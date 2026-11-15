// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

package com.lansi

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.drawable.Icon
import android.media.MediaMetadata
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager

/**
 * What the page reads aloud, as the phone knows it: a session of media, so
 * that the buttons of headphones, of the locked screen and of the
 * notification play and pause it, and a service in the foreground that
 * keeps the app, and the page in it, fetching and playing the sentences
 * while the screen is off, with the processor and the Wi-Fi kept awake
 * while it plays. It lasts as long as the page has a player open (see
 * chat-ui/src/lib/media.ts).
 */
class Speaking : Service() {
    private lateinit var session: MediaSession
    private lateinit var awake: PowerManager.WakeLock
    private lateinit var online: WifiManager.WifiLock

    override fun onCreate() {
        super.onCreate()
        session = MediaSession(this, "Lansi").apply {
            setCallback(object : MediaSession.Callback() {
                override fun onPlay() = ask(PLAY)
                override fun onPause() = ask(PAUSE)
                override fun onSkipToNext() = ask(NEXT)
                override fun onSkipToPrevious() = ask(PREVIOUS)
                override fun onStop() = ask(STOP)
            })
            isActive = true
        }
        awake = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "lansi:speaking")
            .apply { setReferenceCounted(false) }
        @Suppress("DEPRECATION")
        online = applicationContext.getSystemService(WifiManager::class.java)
            .createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "lansi:speaking")
            .apply { setReferenceCounted(false) }
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL, getString(R.string.speaking_channel), NotificationManager.IMPORTANCE_LOW),
        )
        running = this
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent == null) {
            return START_NOT_STICKY
        }
        val action = intent.action ?: return START_NOT_STICKY
        when (action) {
            SHOW -> show(intent.getBooleanExtra(PLAYING, false), intent.getStringExtra(TITLE) ?: "")
            // a button of the notification
            PLAY, PAUSE, NEXT, PREVIOUS, STOP -> ask(action)
        }
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        running = null
        awake.takeIf { it.isHeld }?.release()
        online.takeIf { it.isHeld }?.release()
        session.release()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    /** Shows what is read, and whether it plays, to the phone. */
    fun show(playing: Boolean, title: String) {
        session.setPlaybackState(
            PlaybackState.Builder()
                .setActions(
                    PlaybackState.ACTION_PLAY or PlaybackState.ACTION_PAUSE or PlaybackState.ACTION_PLAY_PAUSE
                        or PlaybackState.ACTION_SKIP_TO_NEXT or PlaybackState.ACTION_SKIP_TO_PREVIOUS
                        or PlaybackState.ACTION_STOP,
                )
                .setState(
                    if (playing) PlaybackState.STATE_PLAYING else PlaybackState.STATE_PAUSED,
                    PlaybackState.PLAYBACK_POSITION_UNKNOWN,
                    1f,
                )
                .build(),
        )
        session.setMetadata(
            MediaMetadata.Builder()
                .putString(MediaMetadata.METADATA_KEY_TITLE, title)
                .putString(MediaMetadata.METADATA_KEY_ARTIST, getString(R.string.app_name))
                .build(),
        )
        if (playing) {
            awake.acquire()
            online.acquire()
        } else {
            awake.takeIf { it.isHeld }?.release()
            online.takeIf { it.isHeld }?.release()
        }
        val opened = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE,
        )
        val notification = Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.ic_lock_silent_mode_off)
            .setContentTitle(title)
            .setContentText(getString(R.string.app_name))
            .setContentIntent(opened)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setOnlyAlertOnce(true)
            .addAction(button(android.R.drawable.ic_media_previous, R.string.previous_sentence, PREVIOUS))
            .addAction(
                if (playing) {
                    button(android.R.drawable.ic_media_pause, R.string.pause, PAUSE)
                } else {
                    button(android.R.drawable.ic_media_play, R.string.play, PLAY)
                },
            )
            .addAction(button(android.R.drawable.ic_media_next, R.string.next_sentence, NEXT))
            .setStyle(Notification.MediaStyle().setMediaSession(session.sessionToken).setShowActionsInCompactView(0, 1, 2))
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIFICATION, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK)
        } else {
            startForeground(NOTIFICATION, notification)
        }
    }

    private fun button(icon: Int, label: Int, action: String): Notification.Action {
        val intent = PendingIntent.getService(
            this,
            action.hashCode(),
            Intent(this, Speaking::class.java).setAction(action),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return Notification.Action.Builder(Icon.createWithResource(this, icon), getString(label), intent).build()
    }

    companion object {
        private const val CHANNEL = "speaking"
        private const val NOTIFICATION = 1
        private const val SHOW = "show"
        private const val PLAYING = "playing"
        private const val TITLE = "title"
        // what the page is asked to do, as it calls it (MediaAction)
        private const val PLAY = "play"
        private const val PAUSE = "pause"
        private const val NEXT = "next"
        private const val PREVIOUS = "previous"
        private const val STOP = "stop"

        private var running: Speaking? = null

        /** What the buttons ask the page to do, while the page is there to be asked. */
        var onAsked: ((String) -> Unit)? = null

        private fun ask(action: String) {
            onAsked?.invoke(action)
        }

        /** Shows what the page reads, starting the service if it is not running. */
        fun show(context: Context, playing: Boolean, title: String) {
            val service = running
            if (service != null) {
                service.show(playing, title)
                return
            }
            try {
                context.startForegroundService(
                    Intent(context, Speaking::class.java).setAction(SHOW).putExtra(PLAYING, playing).putExtra(TITLE, title),
                )
            } catch (e: IllegalStateException) {
                // the app is not in sight, where the phone lets nothing start in the foreground
            }
        }

        /** Lets go of it all, once the page has no player open. */
        fun end(context: Context) {
            context.stopService(Intent(context, Speaking::class.java))
        }
    }
}
