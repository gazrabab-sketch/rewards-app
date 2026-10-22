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
android.archs = arm64-v8a,armeabi-v7a
android.allow_backup = False
android.release_artifact = apk

[buildozer]
log_level = 2
warn_on_root = 1
