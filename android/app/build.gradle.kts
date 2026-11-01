// Copyright: Ankitects Pty Ltd and contributors
// License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

import groovy.json.JsonSlurper

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
}

// Lansi is served at /lansi/ by the nginx of CyanHouse, under the two names
// CyanHouse goes by: PUBLIC_HOST from anywhere, and LAN_HOST at home. Both
// are read from its config.json, next to this repository in sharedCode
// unless the property cyanHouseConfig names another; the properties
// publicHost and lanHost set either one instead.
@Suppress("UNCHECKED_CAST")
val config: Map<String, Any?> = run {
    val path = providers.gradleProperty("cyanHouseConfig").orNull ?: "../../sharedCode/CyanHouse/config.json"
    val file = rootProject.file(path)
    if (file.exists()) JsonSlurper().parse(file) as Map<String, Any?> else emptyMap()
}

fun host(property: String, key: String): String =
    (providers.gradleProperty(property).orNull ?: config[key] as? String ?: "").trim()

val publicHost = host("publicHost", "PUBLIC_HOST")
val lanHost = host("lanHost", "LAN_HOST")
if (publicHost.isEmpty()) {
    logger.warn("No PUBLIC_HOST in CyanHouse's config.json, nor a publicHost property: the app has nowhere to go.")
}

android {
    namespace = "com.lansi"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.lansi"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
        buildConfigField("String", "PUBLIC_URL", "\"https://$publicHost/lansi/\"")
        buildConfigField("String", "LAN_URL", if (lanHost.isEmpty()) "\"\"" else "\"https://$lanHost/lansi/\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
    buildFeatures {
        buildConfig = true
    }
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity)
    implementation(libs.androidx.webkit)
}
