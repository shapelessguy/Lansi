// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

package com.lansi

import android.content.Context
import android.webkit.WebView
import androidx.webkit.ScriptHandler
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import org.json.JSONObject

/**
 * Carries what the web app keeps in its localStorage, the session of whoever
 * logged in above all, from one address of Lansi to the other. Each address
 * is an origin of its own, with a storage of its own, so without this the
 * app would ask to log in again whenever it went from home to the internet
 * or back.
 *
 * The page sends its storage here whenever it changes, and it is kept with
 * the origin it came from. Before the page of the other origin runs, the
 * storage kept is put in place of its own; the page of the same origin
 * already has it.
 */
class Storage(context: Context) {
    private val prefs = context.getSharedPreferences("web_storage", Context.MODE_PRIVATE)
    private var script: ScriptHandler? = null

    fun attach(webView: WebView) {
        // in a WebView too old for either, each address keeps its own storage
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)
            || !WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)
        ) {
            return
        }
        WebViewCompat.addWebMessageListener(webView, "lansiAndroid", Route.origins) { _, message, origin, isMainFrame, _ ->
            val items = message.data
            if (isMainFrame && items != null) {
                prefs.edit().putString(ORIGIN, origin.toString()).putString(ITEMS, items).apply()
                register(webView)
            }
        }
        register(webView)
    }

    /** Has the pages that load from now on start from the storage kept now. */
    private fun register(webView: WebView) {
        script?.remove()
        script = WebViewCompat.addDocumentStartJavaScript(webView, source(), Route.origins)
    }

    private fun source(): String {
        val origin = prefs.getString(ORIGIN, null)
        val items = prefs.getString(ITEMS, null)
        val kept = if (origin != null && items != null) {
            "{ origin: ${JSONObject.quote(origin)}, items: JSON.parse(${JSONObject.quote(items)}) }"
        } else {
            "null"
        }
        return SCRIPT.replace("KEPT", kept)
    }

    private companion object {
        const val ORIGIN = "origin"
        const val ITEMS = "items"

        val SCRIPT = """
            (() => {
                const kept = KEPT;
                try {
                    if (kept && kept.origin !== location.origin) {
                        localStorage.clear();
                        for (const [key, value] of Object.entries(kept.items)) {
                            localStorage.setItem(key, value);
                        }
                    }
                } catch {
                    // without storage the page asks to log in, as in a browser
                }
                let sent = null;
                function send() {
                    try {
                        const items = {};
                        for (let i = 0; i < localStorage.length; i++) {
                            const key = localStorage.key(i);
                            items[key] = localStorage.getItem(key);
                        }
                        const text = JSON.stringify(items);
                        if (text !== sent) {
                            sent = text;
                            lansiAndroid.postMessage(text);
                        }
                    } catch {
                        // tried again in a moment
                    }
                }
                setInterval(send, 2000);
                addEventListener("pagehide", send);
                document.addEventListener("visibilitychange", send);
            })();
        """.trimIndent()
    }
}
