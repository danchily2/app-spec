"""Detect an app's stack and platforms from its files."""

import json
import os

from .common import read_text


def detect(root):
    """Return {stack, platforms, evidence}. stack: react-native | ios-native | android-native | flutter | other."""
    root = os.path.realpath(root)
    evidence = []
    pkg = {}
    text = read_text(os.path.join(root, "package.json"))
    if text:
        try:
            pkg = json.loads(text)
        except ValueError:
            pkg = {}
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    has_ios = os.path.isdir(os.path.join(root, "ios"))
    has_android = os.path.isdir(os.path.join(root, "android"))
    if "react-native" in deps:
        evidence.append(f"package.json depends on react-native {deps['react-native']}")
        if "expo" in deps:
            evidence.append(f"Expo {deps['expo']}")
        platforms = [p for p, ok in (("ios", has_ios or "expo" in deps), ("android", has_android or "expo" in deps)) if ok]
        return {"stack": "react-native", "platforms": platforms or ["ios", "android"], "evidence": evidence}
    if os.path.isfile(os.path.join(root, "pubspec.yaml")) and "flutter" in (read_text(os.path.join(root, "pubspec.yaml")) or ""):
        evidence.append("pubspec.yaml declares flutter")
        return {"stack": "flutter", "platforms": [p for p, ok in (("ios", has_ios), ("android", has_android)) if ok],
                "evidence": evidence}
    if "@capacitor/core" in deps or "@ionic/angular" in deps or "cordova-ios" in deps:
        evidence.append("hybrid web shell (Capacitor, Ionic or Cordova)")
        return {"stack": "other", "platforms": [p for p, ok in (("ios", has_ios), ("android", has_android)) if ok],
                "evidence": evidence}

    xcodeproj, gradle_app = [], False
    for dirpath, dirnames, filenames in os.walk(root):
        depth = os.path.relpath(dirpath, root).count(os.sep)
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "Pods", "build", ".build", ".gradle"}
                       and not d.endswith((".xcodeproj", ".xcworkspace", ".xcassets"))] if depth < 2 else []
        for d in os.listdir(dirpath):
            if d.endswith(".xcodeproj") and d != "Pods.xcodeproj":
                xcodeproj.append(os.path.relpath(os.path.join(dirpath, d), root))
        for f in filenames:
            if f in ("build.gradle", "build.gradle.kts"):
                body = read_text(os.path.join(dirpath, f)) or ""
                if "com.android.application" in body or "android.application" in body or "applicationId" in body:
                    gradle_app = True
    if xcodeproj and not gradle_app:
        evidence.append("Xcode project: " + ", ".join(sorted(set(xcodeproj))[:3]))
        return {"stack": "ios-native", "platforms": ["ios"], "evidence": evidence}
    if gradle_app and not xcodeproj:
        evidence.append("Gradle Android application module")
        return {"stack": "android-native", "platforms": ["android"], "evidence": evidence}
    if os.path.isfile(os.path.join(root, "Package.swift")):
        evidence.append("Swift package at the root")
        return {"stack": "ios-native", "platforms": ["ios"], "evidence": evidence}
    if xcodeproj and gradle_app:
        evidence.append("both an Xcode project and an Android application module (a monorepo?)")
    return {"stack": "other", "platforms": [], "evidence": evidence or ["no mobile manifest recognized"]}
