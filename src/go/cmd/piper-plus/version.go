package main

import rdebug "runtime/debug"

// version is set at build time with -ldflags "-X main.version=<version>"
// (see src/go/Makefile). When it is empty, --version reports the module
// version that `go install github.com/ayutaz/piper-plus/src/go/cmd/piper-plus@vX.Y.Z`
// records in the binary.
var version string

// versionLine is what --version prints.
func versionLine() string {
	return "piper-plus (Go) " + resolveVersion(version, rdebug.ReadBuildInfo)
}

func resolveVersion(ldflagsVersion string, readBuildInfo func() (*rdebug.BuildInfo, bool)) string {
	if ldflagsVersion != "" {
		return ldflagsVersion
	}
	if info, ok := readBuildInfo(); ok && info.Main.Version != "" {
		return info.Main.Version
	}
	return "(devel)"
}
