#pragma once

// FIRMWARE_VERSION and FIRMWARE_BUILD_ID are injected per env by
// scripts/version.py from version/<env>.txt and git. The fallbacks only apply
// to builds that bypass PlatformIO.
#ifndef FIRMWARE_VERSION
#define FIRMWARE_VERSION "0.0.0"
#endif
#ifndef FIRMWARE_BUILD_ID
#define FIRMWARE_BUILD_ID "unknown"
#endif
// Bump the major number for incompatible protocol changes (see docs/PROTOCOL.md).
#define PROTOCOL_VERSION 1
