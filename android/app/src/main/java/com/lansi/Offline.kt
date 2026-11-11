// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

package com.lansi

import android.content.Context
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import java.io.ByteArrayInputStream
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

/**
 * What the app keeps of Lansi on the phone, to open it and read the books
 * kept offline without a connection: the files of the page itself, and
 * what the checker server answers that the page marks to be kept (see
 * chat-ui/src/lib/offlineCache.ts). It is kept once, in the files of the
 * app, whichever of the two addresses it came by, rather than by the
 * WebView for each of them.
 *
 * Each thing is asked of the server first, and kept as it comes; the one
 * kept is given when the server cannot be reached, or at once when the
 * page asks for it so. The page also reads and writes text kept here, and
 * lets go of a book, through `lansiOffline` (Bridge).
 */
class Offline(context: Context) {
    private val root = File(context.filesDir, "offline")
    private val context = context.applicationContext

    fun attach(webView: WebView) {
        webView.addJavascriptInterface(Bridge(), "lansiOffline")
    }

    /** The answer to a request of the page, if the app gives it, or null to have the WebView ask for it itself. */
    fun intercept(request: WebResourceRequest): WebResourceResponse? {
        if (request.method != "GET" || !Route.isLansi(request.url)) {
            return null
        }
        val path = request.url.encodedPath ?: return null
        if (path.startsWith("$CHECKER/")) {
            // only what the page marks is kept, as whoever is logged in
            val mode = header(request, MODE) ?: return null
            val user = header(request, USER) ?: return null
            val place = placeOf(userRoot(user), path.removePrefix(CHECKER)) ?: return null
            return answer(request, place, mode)
        }
        if (path.startsWith("/lansi/")) {
            // the page changes as it is worked on, and is kept as it was last, without the times it was changed at
            val query = request.url.encodedQuery?.split("&")?.filterNot { it.startsWith("t=") }?.joinToString("&")
            val place = placeOf(File(root, "app"), if (query.isNullOrEmpty()) path else "$path?$query") ?: return null
            return answer(request, place, KEEP)
        }
        return null
    }

    private fun answer(request: WebResourceRequest, place: File, mode: String): WebResourceResponse? {
        if (mode == ONLY) {
            return kept(place) ?: missing()
        }
        if (mode == FIRST || !Route.online(context)) {
            kept(place)?.let { return it }
        }
        val connection = try {
            open(request)
        } catch (e: IOException) {
            return kept(place)
        }
        try {
            val status = connection.responseCode
            val type = connection.contentType ?: "application/octet-stream"
            if (status in 502..504 || status in 300..399) {
                kept(place)?.let { return it }
            }
            if (status in 300..399) {
                return null
            }
            remember(connection)
            val body = if (status < 400) {
                connection.inputStream.use { it.readBytes() }
            } else {
                connection.errorStream?.use { it.readBytes() } ?: ByteArray(0)
            }
            if (status == 200) {
                save(place, body, type)
            }
            return response(status, connection.responseMessage, type, body, headersOf(connection))
        } catch (e: IOException) {
            return kept(place)
        } finally {
            connection.disconnect()
        }
    }

    /** Asks the server as the page would have, but for what only the app understands, and anything conditional. */
    private fun open(request: WebResourceRequest): HttpURLConnection {
        val url = request.url.toString()
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = 10_000
        // the server waits up to 50 seconds for audio that is being made
        connection.readTimeout = 70_000
        for ((name, value) in request.requestHeaders) {
            if (name.lowercase() !in LEFT_OUT && !name.lowercase().startsWith("x-lansi-")) {
                connection.setRequestProperty(name, value)
            }
        }
        CookieManager.getInstance().getCookie(url)?.let { connection.setRequestProperty("Cookie", it) }
        return connection
    }

    /** Keeps the cookies the server set, as the WebView would have. */
    private fun remember(connection: HttpURLConnection) {
        val url = connection.url.toString()
        connection.headerFields["Set-Cookie"]?.forEach { CookieManager.getInstance().setCookie(url, it) }
    }

    private fun headersOf(connection: HttpURLConnection): Map<String, String> =
        connection.headerFields
            .filterKeys { it != null && it.lowercase() !in NOT_PASSED }
            .mapKeys { it.key!! }
            .mapValues { it.value.joinToString(", ") }

    private fun response(
        status: Int,
        reason: String?,
        type: String,
        body: ByteArray,
        headers: Map<String, String>,
    ): WebResourceResponse {
        val mime = type.substringBefore(";").trim()
        val charset = Regex("charset=\"?([^;\"]+)", RegexOption.IGNORE_CASE).find(type)?.groupValues?.get(1)
        return WebResourceResponse(
            mime,
            charset,
            status,
            reason?.takeIf { it.isNotBlank() } ?: "OK",
            headers,
            ByteArrayInputStream(body),
        )
    }

    private fun kept(place: File): WebResourceResponse? {
        val body = File(place, BODY)
        if (!body.exists()) {
            return null
        }
        val type = File(place, TYPE).takeIf { it.exists() }?.readText() ?: "application/octet-stream"
        return try {
            response(200, "OK", type, body.readBytes(), mapOf("X-Lansi-Kept" to "1"))
        } catch (e: IOException) {
            null
        }
    }

    private fun missing(): WebResourceResponse =
        response(404, "Not Found", "application/json", "{\"error\": \"not kept\"}".toByteArray(), emptyMap())

    /** Keeps what came for a place, whole or not at all. */
    private fun save(place: File, body: ByteArray, type: String) {
        try {
            place.mkdirs()
            // the same thing may come twice at once, each written apart
            val written = File.createTempFile(BODY, ".new", place)
            written.writeBytes(body)
            File(place, TYPE).writeText(type)
            if (!written.renameTo(File(place, BODY))) {
                written.delete()
            }
        } catch (e: IOException) {
            // the phone is full, and it is asked of the server the next time
        }
    }

    private fun userRoot(user: String): File = File(File(root, "users"), encode(user))

    /**
     * Where what is kept of a path is, as a folder: each of its parts a
     * folder within the one before, as what is kept of `/books/b` and of
     * `/books/b/notes` both are, with the body of the answer and its kind in it.
     */
    private fun placeOf(base: File, path: String): File? {
        val parts = path.split("/").filter { it.isNotEmpty() }.map(::encode)
        if (parts.any { it == "." || it == ".." }) {
            return null
        }
        return parts.fold(base) { folder, part -> File(folder, part) }
    }

    private fun encode(part: String): String = URLEncoder.encode(part, "UTF-8")

    private fun header(request: WebResourceRequest, name: String): String? =
        request.requestHeaders.entries.firstOrNull { it.key.equals(name, ignoreCase = true) }?.value

    /** What the page asks of what is kept, by the user it is kept for and the path on the checker server. */
    private inner class Bridge {
        /** Text kept under a path, or null. */
        @JavascriptInterface
        fun read(user: String, path: String): String? =
            placeOf(userRoot(user), path)?.let { File(it, BODY) }?.takeIf { it.exists() }?.readText()

        @JavascriptInterface
        fun write(user: String, path: String, text: String) {
            placeOf(userRoot(user), path)?.let { save(it, text.toByteArray(), "application/json") }
        }

        /** Lets go of what is kept under a path, but not of what is kept under the paths within it. */
        @JavascriptInterface
        fun remove(user: String, path: String) {
            placeOf(userRoot(user), path)?.let {
                File(it, BODY).delete()
                File(it, TYPE).delete()
            }
        }

        /** Lets go of all that is kept of a book but its cover. */
        @JavascriptInterface
        fun forget(user: String, bookId: String) {
            val book = placeOf(userRoot(user), "/books/$bookId") ?: return
            book.listFiles()?.filter { it.name != "cover" }?.forEach { it.deleteRecursively() }
        }
    }

    private companion object {
        const val CHECKER = "/lansi/checker"
        const val MODE = "X-Lansi-Offline"
        const val USER = "X-Lansi-User"
        // what the page asks for: what is kept alone, what is kept before the server, or the server first
        const val ONLY = "only"
        const val FIRST = "first"
        const val KEEP = "keep"
        // the names in the folder of a path; no part of a path is encoded to them
        const val BODY = "%body"
        const val TYPE = "%type"
        val LEFT_OUT = setOf("if-none-match", "if-modified-since", "range", "accept-encoding", "cookie")
        val NOT_PASSED = setOf("content-length", "content-encoding", "transfer-encoding", "content-type", "set-cookie")
    }
}
