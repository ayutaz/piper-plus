# Android AAR Release Process

## Prerequisites

- Sonatype Central Portal account (https://central.sonatype.com/)
- GPG key pair for signing
- Repository admin access for GitHub Secrets

## GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `MAVEN_CENTRAL_USERNAME` | Sonatype Central Portal username (or token) |
| `MAVEN_CENTRAL_PASSWORD` | Sonatype Central Portal password (or token) |
| `GPG_SIGNING_KEY` | Base64-encoded GPG private key (`gpg --export-secret-keys <KEY_ID> | base64`) |
| `GPG_SIGNING_PASSWORD` | Passphrase for the GPG key |

## Release Steps

1. **Update version**: Edit `src/android/gradle.properties` and set `VERSION_NAME=X.Y.Z`
2. **Commit**: `git commit -am "release: Android v X.Y.Z"`
3. **Tag**: `git tag android-vX.Y.Z`
4. **Push**: `git push origin dev --tags`
5. **Create GitHub Release**: Go to GitHub Releases, create a new release from the `android-vX.Y.Z` tag
6. **CI automatically publishes**: The `android-publish.yml` workflow triggers and publishes to Maven Central

## What the CI Does

1. Validates all 4 secrets are present
2. Validates `VERSION_NAME` matches the git tag
3. Builds release AAR
4. Runs Android Lint
5. Runs unit tests
6. Signs all publications with GPG
7. Publishes to Maven Central via Sonatype Central Portal

## Maven Central Coordinates

```
io.github.ayousanz:piper-android:X.Y.Z
```

## Verification

After publishing, verify the artifact is available:
```bash
curl -s "https://repo1.maven.org/maven2/io/github/ayousanz/piper-android/X.Y.Z/" | head -20
```

Note: Maven Central propagation may take 10-30 minutes.

## Native Library Build (Pre-requisite)

Before releasing, native `.so` files must be pre-built and placed in `src/main/jniLibs/`:

```bash
# Build for all ABIs
ONNXRUNTIME_DIR=/path/to/onnxruntime-android \
OPENJTALK_DIR=/path/to/openjtalk-android \
SPDLOG_DIR=/path/to/spdlog \
FMT_DIR=/path/to/fmt \
./scripts/build-android-arm64-v8a.sh

# Repeat for armeabi-v7a and x86_64
# Then copy .so files:
cp install-android-arm64-v8a/lib/arm64-v8a/*.so src/main/jniLibs/arm64-v8a/
```

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `Version mismatch` | gradle.properties != git tag | Ensure VERSION_NAME matches tag |
| `GPG_SIGNING_KEY not set` | Missing secret | Add GPG key to GitHub Secrets |
| `401 Unauthorized` | Invalid Maven credentials | Verify Sonatype credentials |
| `Duplicate version` | Already published | Bump version number |
