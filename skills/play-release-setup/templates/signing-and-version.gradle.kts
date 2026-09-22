// ============================================================================================
// Paste the top-level section near the top of the app module's build.gradle.kts, after the
// plugins block. Add `import java.util.Properties` to the file's imports.
// ============================================================================================

// Release signing credentials. Locally they come from a gitignored keystore.properties at the
// repo root; in CI the same four values arrive as environment variables. Both lookups are
// configuration-cache safe. When neither source supplies them the release build stays unsigned,
// so a fresh clone can still verify that a release build compiles.
val keystoreProperties: Map<String, String> = providers.fileContents(
    rootProject.layout.projectDirectory.file("keystore.properties")
).asText.map { text ->
    Properties().apply { load(text.reader()) }
        .entries.associate { (key, value) -> key.toString() to value.toString() }
}.getOrElse(emptyMap())

fun signingValue(propertyName: String, environmentName: String): String? =
    keystoreProperties[propertyName]?.takeIf { it.isNotBlank() }
        ?: providers.environmentVariable(environmentName).orNull?.takeIf { it.isNotBlank() }

val releaseStoreFile = signingValue("storeFile", "KEYSTORE_FILE")
val releaseStorePassword = signingValue("storePassword", "KEYSTORE_PASSWORD")
val releaseKeyAlias = signingValue("keyAlias", "KEY_ALIAS")
val releaseKeyPassword = signingValue("keyPassword", "KEY_PASSWORD")
val hasReleaseSigning = releaseStoreFile != null && releaseStorePassword != null &&
        releaseKeyAlias != null && releaseKeyPassword != null

// The one value a release PR edits. versionCode is derived from it so the two can never drift:
// 1.2.3 -> base + 10203. Play only requires codes to increase, so gaps are harmless - but a
// published code is retired forever, so versionCodeBase may only ever go up.
val appVersionName = "__VERSION_NAME__"
val versionCodeBase = __VERSION_CODE_BASE__
val appVersionCode = run {
    val parts = appVersionName.split(".")
    require(parts.size in 2..3 && parts.all { it.toIntOrNull() != null }) {
        "versionName must be MAJOR.MINOR or MAJOR.MINOR.PATCH, was \"$appVersionName\""
    }
    val (major, minor, patch) = List(3) { parts.getOrNull(it)?.toInt() ?: 0 }
    require(minor < 100 && patch < 100) {
        "minor and patch must each stay under 100 to keep versionCode ordered, was \"$appVersionName\""
    }
    versionCodeBase + major * 10_000 + minor * 100 + patch
}

// Read by the release workflow to check the pushed tag against the build file, so the check
// does not depend on how the version literal happens to be formatted.
tasks.register("printVersionName") {
    val versionName = appVersionName
    doLast { println(versionName) }
}

// ============================================================================================
// Inside android { ... }
// ============================================================================================

//  defaultConfig {
//      versionCode = appVersionCode
//      versionName = appVersionName
//  }
//
//  signingConfigs {
//      if (hasReleaseSigning) {
//          create("release") {
//              storeFile = file(releaseStoreFile!!)
//              storePassword = releaseStorePassword
//              keyAlias = releaseKeyAlias
//              keyPassword = releaseKeyPassword
//          }
//      }
//  }
//
//  buildTypes {
//      release {
//          if (hasReleaseSigning) {
//              signingConfig = signingConfigs.getByName("release")
//          }
//      }
//  }
