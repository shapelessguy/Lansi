// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

package com.lansi

import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.content.Context
import android.graphics.Rect
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.ActionMode
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import androidx.activity.ComponentActivity
import androidx.activity.addCallback
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

/**
 * Lansi as the web shows it, in a WebView: the app is the page at /lansi/
 * of the server of CyanHouse, which has its own login and phone layout.
 * What the app adds is the choice of address (Route), keeping the login
 * from one address to the other (Storage), the picker of files for the
 * books, links out of Lansi opened in the browser, and text selected
 * without the phone's own menu over it, since Lansi has its own (Page).
 */
class MainActivity : ComponentActivity() {
    private lateinit var webView: WebView
    private val handler = Handler(Looper.getMainLooper())
    // the page could not be loaded, and is tried again while the app is in sight
    private var failed = false
    private var picking: ValueCallback<Array<Uri>>? = null
    private val pickFiles = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        picking?.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result.resultCode, result.data))
        picking = null
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        webView = Page(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            webViewClient = Client()
            webChromeClient = Chrome()
        }
        // the page is kept clear of the bars of the system and of the keyboard
        val frame = FrameLayout(this).apply { addView(webView) }
        ViewCompat.setOnApplyWindowInsetsListener(frame) { view, insets ->
            val bars = insets.getInsets(
                WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout()
                    or WindowInsetsCompat.Type.ime(),
            )
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            WindowInsetsCompat.CONSUMED
        }
        setContentView(frame)
        Storage(this).attach(webView)
        onBackPressedDispatcher.addCallback(this) {
            if (webView.canGoBack()) {
                webView.goBack()
            } else {
                isEnabled = false
                onBackPressedDispatcher.onBackPressed()
                isEnabled = true
            }
        }
        load()
    }

    override fun onResume() {
        super.onResume()
        if (failed) {
            load()
        }
    }

    override fun onPause() {
        super.onPause()
        handler.removeCallbacksAndMessages(null)
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        webView.destroy()
        super.onDestroy()
    }

    /** Opens Lansi at the address that answers now. */
    private fun load() {
        failed = false
        Thread {
            val url = Route.pick(this)
            runOnUiThread {
                if (!isDestroyed) {
                    webView.loadUrl(url)
                }
            }
        }.start()
    }

    private inner class Client : WebViewClient() {
        override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
            if (Route.isLansi(request.url)) {
                return false
            }
            try {
                startActivity(Intent(Intent.ACTION_VIEW, request.url))
            } catch (e: ActivityNotFoundException) {
                // nothing on the phone opens it
            }
            return true
        }

        // The address in use no longer answers, as when the phone left the
        // Wi-Fi at home: it is chosen again in a moment.
        override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
            if (request.isForMainFrame && !failed) {
                failed = true
                handler.postDelayed(::load, 3000)
            }
        }
    }

    private inner class Chrome : WebChromeClient() {
        override fun onShowFileChooser(
            view: WebView,
            callback: ValueCallback<Array<Uri>>,
            params: FileChooserParams,
        ): Boolean {
            picking?.onReceiveValue(null)
            picking = callback
            return try {
                pickFiles.launch(params.createIntent())
                true
            } catch (e: ActivityNotFoundException) {
                picking = null
                false
            }
        }
    }
}

/**
 * The WebView of the page, which selects text as any does, with its
 * handles, but without the phone's menu of copying and sharing over the
 * selection: the page brings up its own buttons there, which the menu
 * would cover.
 */
private class Page(context: Context) : WebView(context) {
    override fun startActionMode(callback: ActionMode.Callback, type: Int): ActionMode? =
        super.startActionMode(WithoutItems(callback), type)
}

/**
 * The menu of a selection with nothing in it, which the phone then does
 * not show. The selection stays as it is, since the menu is still made.
 */
private class WithoutItems(private val wrapped: ActionMode.Callback) : ActionMode.Callback2() {
    override fun onCreateActionMode(mode: ActionMode, menu: Menu): Boolean {
        wrapped.onCreateActionMode(mode, menu)
        menu.clear()
        return true
    }

    override fun onPrepareActionMode(mode: ActionMode, menu: Menu): Boolean {
        wrapped.onPrepareActionMode(mode, menu)
        menu.clear()
        return true
    }

    override fun onActionItemClicked(mode: ActionMode, item: MenuItem): Boolean =
        wrapped.onActionItemClicked(mode, item)

    override fun onDestroyActionMode(mode: ActionMode) = wrapped.onDestroyActionMode(mode)

    override fun onGetContentRect(mode: ActionMode, view: View, outRect: Rect) {
        if (wrapped is ActionMode.Callback2) {
            wrapped.onGetContentRect(mode, view, outRect)
        } else {
            super.onGetContentRect(mode, view, outRect)
        }
    }
}
