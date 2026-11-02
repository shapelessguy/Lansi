// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

package com.lansi

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import java.io.IOException
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.URL
import java.util.concurrent.CompletableFuture
import java.util.concurrent.TimeUnit

/**
 * Which of the two addresses of Lansi the app opens: the one at home
 * (LAN_URL, a name set to the server's address on the LAN) when the phone is
 * on a Wi-Fi whose addresses hold the one that name points at and it answers
 * from there, and the one on the internet (PUBLIC_URL) otherwise, at once. Both are the same site, with a certificate of its own; they come
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
        if (LAN_URL.isNotEmpty() && onHomeNetwork(context) && answers(LAN_URL)) LAN_URL else PUBLIC_URL

    /**
     * Whether the phone is on a Wi-Fi whose addresses hold the one the name at
     * home points at: on any other network that address is not there, and
     * asking it would only keep the page waiting.
     */
    private fun onHomeNetwork(context: Context): Boolean {
        val connectivity = context.getSystemService(ConnectivityManager::class.java) ?: return false
        val network = connectivity.activeNetwork ?: return false
        val capabilities = connectivity.getNetworkCapabilities(network) ?: return false
        if (!capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
            && !capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)
        ) {
            return false
        }
        val links = connectivity.getLinkProperties(network)?.linkAddresses ?: return false
        val home = resolve(Uri.parse(LAN_URL).host ?: return false)
        return home.any { address -> links.any { within(address, it.address, it.prefixLength) } }
    }

    /** The addresses `host` points at, or none if they are not known within a second. */
    private fun resolve(host: String): List<InetAddress> = try {
        CompletableFuture.supplyAsync { InetAddress.getAllByName(host).toList() }.get(1, TimeUnit.SECONDS)
    } catch (e: Exception) {
        emptyList()
    }

    /** Whether `address` is on the network of `link`, whose first `prefix` bits are the network's. */
    private fun within(address: InetAddress, link: InetAddress, prefix: Int): Boolean {
        val a = address.address
        val b = link.address
        if (a.size != b.size) {
            return false
        }
        for (bit in 0 until prefix) {
            val mask = 0x80 ushr (bit % 8)
            if ((a[bit / 8].toInt() and mask) != (b[bit / 8].toInt() and mask)) {
                return false
            }
        }
        return true
    }

    /**
     * Whether anything answers at `url`, quickly: at home the server answers
     * at once, and a network that only looks like home, such as another
     * router with the same addresses, should not keep the page waiting.
     */
    private fun answers(url: String): Boolean = try {
        val connection = URL(url).openConnection() as HttpURLConnection
        connection.connectTimeout = 500
        connection.readTimeout = 500
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
