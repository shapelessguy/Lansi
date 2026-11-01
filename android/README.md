# Lansi for Android

The web GUI (`chat-ui/`) in a WebView: the app opens `/lansi/` on the server
of CyanHouse, logs in with the web's own login (a CyanHouse user whose
`Lansi` permission is true), and lays itself out as the web does on a
phone. There is nothing of Lansi's own in it to keep up with the web.

What the app adds to the page:

- `Route.kt`: the address. CyanHouse goes by two names, `LAN_HOST` at home
  and `PUBLIC_HOST` from anywhere; the app opens the one at home when it
  answers from the Wi-Fi the phone is on, and the other otherwise, and
  chooses again when the page can no longer be loaded.
- `Storage.kt`: the login kept from one name to the other. Each is an
  origin with a localStorage of its own, so the storage of the web app is
  carried over whenever the app goes from one to the other.
- `MainActivity.kt`: the picker of files for the EPUB books, links out of
  Lansi opened in the browser, Back going back in the page, and the page
  kept clear of the bars of the system and the keyboard.

## Build

```bash
just android
```

builds `app/build/outputs/apk/debug/app-debug.apk`. It needs the Android SDK,
named by `sdk.dir` in `android/local.properties` (Android Studio writes it),
and a JDK from 17 to 21 (`JAVA_HOME`, or `java` on the `PATH`): Gradle 8.11
does not run on the newer one that comes with Android Studio.

The two names are read from CyanHouse's `config.json`, at
`../sharedCode/CyanHouse/config.json` next to this repository unless
`-PcyanHouseConfig=<path>` names another; `-PpublicHost=` and `-PlanHost=`
set either one instead. They are built into the app, so it is built again
when they change.
