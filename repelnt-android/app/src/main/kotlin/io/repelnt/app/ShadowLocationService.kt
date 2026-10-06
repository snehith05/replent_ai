package io.repelnt.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.location.Criteria
import android.location.Location
import android.location.LocationManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import io.repelnt.core.ShadowIdentity

/**
 * Feeds the shadow identity's position to every app on the device.
 *
 * This is the one place on stock Android where a third-party app can actually
 * substitute another app's data rather than merely block it. Registering a test
 * provider replaces the real GPS fix system-wide: Maps, a weather app, an ad SDK
 * all receive these coordinates and have no way to tell they are false.
 *
 * It needs the mock-location appop. A user grants it by picking this app under
 * developer options; software built into the OS grants it to itself with
 * WRITE_SECURE_SETTINGS. The capability is identical either way -- only who is
 * allowed to turn it on differs, which is the whole argument for shipping this
 * inside the system rather than beside it.
 */
class ShadowLocationService : Service() {

    private val handler = Handler(Looper.getMainLooper())
    private lateinit var shadow: ShadowIdentity
    private lateinit var locations: LocationManager
    private var running = false

    private val push = object : Runnable {
        override fun run() {
            publish()
            handler.postDelayed(this, PUSH_INTERVAL_MS)
        }
    }

    override fun onCreate() {
        super.onCreate()
        shadow = ShadowIdentity.derive(PolicyStore(this).deviceSeed)
        locations = getSystemService(Context.LOCATION_SERVICE) as LocationManager
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        startForeground(NOTIFICATION_ID, notification())
        if (!running) {
            running = installProvider()
            if (running) handler.post(push)
        }
        return START_STICKY
    }

    /** Replace the real GPS provider with one we control. */
    private fun installProvider(): Boolean = try {
        runCatching { locations.removeTestProvider(PROVIDER) }
        @Suppress("DEPRECATION")
        locations.addTestProvider(
            PROVIDER,
            /* requiresNetwork = */ false,
            /* requiresSatellite = */ false,
            /* requiresCell = */ false,
            /* hasMonetaryCost = */ false,
            /* supportsAltitude = */ true,
            /* supportsSpeed = */ true,
            /* supportsBearing = */ true,
            Criteria.POWER_LOW,
            Criteria.ACCURACY_FINE,
        )
        locations.setTestProviderEnabled(PROVIDER, true)
        Log.i(TAG, "test provider installed on $PROVIDER")
        true
    } catch (e: SecurityException) {
        // Expected until the appop is granted. Says plainly what is missing
        // rather than failing silently.
        Log.w(TAG, "not the mock location app yet: ${e.message}")
        false
    } catch (e: IllegalArgumentException) {
        Log.w(TAG, "provider unavailable: ${e.message}")
        false
    }

    private fun publish() {
        val tick = (SystemClock.elapsedRealtime() / 3_600_000L).toInt()
        val (lat, lon) = shadow.location(tick)
        val fix = Location(PROVIDER).apply {
            latitude = lat
            longitude = lon
            altitude = 12.0
            accuracy = 4f
            bearing = 0f
            speed = 0f
            time = System.currentTimeMillis()
            elapsedRealtimeNanos = SystemClock.elapsedRealtimeNanos()
        }
        try {
            locations.setTestProviderLocation(PROVIDER, fix)
            Log.i(TAG, "served $lat, $lon as ${shadow.name} in ${shadow.city}")
        } catch (e: SecurityException) {
            Log.w(TAG, "lost mock location permission: ${e.message}")
            running = false
            handler.removeCallbacks(push)
        } catch (e: IllegalArgumentException) {
            Log.w(TAG, "provider went away: ${e.message}")
            running = false
            handler.removeCallbacks(push)
        }
    }

    override fun onDestroy() {
        handler.removeCallbacks(push)
        runCatching { locations.removeTestProvider(PROVIDER) }
        running = false
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun notification(): Notification {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL, "Shadow location",
                    NotificationManager.IMPORTANCE_LOW)
            )
        }
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL)
        } else {
            @Suppress("DEPRECATION") Notification.Builder(this)
        }
        return builder
            .setContentTitle("Repelnt is running")
            .setContentText("${shadow.city} is being reported to every app")
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setOngoing(true)
            .build()
    }

    companion object {
        const val TAG = "RepelntLocation"
        const val ACTION_STOP = "io.repelnt.app.STOP"
        private const val PROVIDER = LocationManager.GPS_PROVIDER
        private const val CHANNEL = "repelnt.location"
        private const val NOTIFICATION_ID = 1
        private const val PUSH_INTERVAL_MS = 2_000L

        fun start(context: Context) {
            val intent = Intent(context, ShadowLocationService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.startService(
                Intent(context, ShadowLocationService::class.java).setAction(ACTION_STOP)
            )
        }
    }
}
