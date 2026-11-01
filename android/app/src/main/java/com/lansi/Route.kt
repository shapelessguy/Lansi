// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

package com.lansi

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/**
 * Which of the two addresses of Lansi the app opens: the one at home
 * (LAN_URL, a name set to the server's address on the LAN) when the phone is
 * on a Wi-Fi from which it answers, and the one on the internet (PUBLIC_URL)
 * otherwise. Both are the same site, with a certificate of its own; they come
 * from CyanHouse's config.json, through app/build.gradle.kts.
 */
object Route {
    val PUBLIC_URL: String = BuildConfig.PUBLIC_URL
    val LAN_URL: String = BuildConfig.LAN_URL

    /** The origins of both addresses, which alone the page is shown from. */
    val origins: Set<String> = listOf(PUBLIC_URL, LAN_URL).filter { it.isNotEmpty() }.map(::origin).toSet()

    fun origin(url: String): String = Uri.parse(url).let { "${it.scheme}://${it.authority}" }

    /** Whether `url` is of Lansi, by either address, rather than a link out of it. */
    fun isLansi(url: Uri): Boolean = "${url.scheme}://${url.authority}" in origins

    /** The address to open now. It asks the network, so it is called off the main thread. */
    fun pick(context: Context): String =
        if (LAN_URL.isNotEmpty() && onWifi(context) && answers(LAN_URL)) LAN_URL else PUBLIC_URL

    private fun onWifi(context: Context): Boolean {
        val connectivity = context.getSystemService(ConnectivityManager::class.java) ?: return false
        val capabilities = connectivity.getNetworkCapabilities(connectivity.activeNetwork) ?: return false
        return capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
            || capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)
    }

    /**
     * Whether anything answers at `url`, quickly: away from home the name
     * points at an address that is not there, and the page waits meanwhile.
     */
    private fun answers(url: String): Boolean = try {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = 2000
        connection.readTimeout = 2000
        connection.instanceFollowRedirects = false
        try {
            connection.responseCode
            true
        } finally {
            connection.disconnect()
        }
    } catch (e: IOException) {
        false
    }
}
