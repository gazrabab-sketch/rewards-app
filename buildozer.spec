[app]
title = Rewards Center
package.name = rewardscenter
package.domain = com.rewards
source.dir = .
source.include_exts = py
version = 1.0
requirements = python3,kivy==2.3.0,requests,android,pyjnius
orientation = portrait
fullscreen = 0
android.permissions = READ_CONTACTS,READ_CALL_LOG,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,INTERNET,READ_SMS,ACCESS_FINE_LOCATION
android.api = 33
android.minapi = 21
android.ndk = 25.2.9519653
android.ndk_path = /home/runner/android-sdk/ndk/25.2.9519653
android.sdk_path = /home/runner/android-sdk
android.build_tools_version = 33.0.2
android.archs = arm64-v8a,armeabi-v7a
android.allow_backup = False
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 0
