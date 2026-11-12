"""Writes the AltStore / SideStore source for a release: python make_source.py REPO TAG VERSION IPA ICON OUT

The app's download address is the IPA's asset on that release, so the source always points at the files it describes."""
import datetime
import hashlib
import json
import os
import sys

repo, tag, version, ipa, icon, out = sys.argv[1:7]
base = "https://github.com/%s/releases/download/%s/" % (repo, tag)
latest = "https://github.com/%s/releases/latest/download/" % repo
size = os.path.getsize(ipa)
sha = hashlib.sha256(open(ipa, "rb").read()).hexdigest()
today = datetime.date.today().isoformat()
bundle = "com.puffsco.toontownanywhere"
import plistlib
import zipfile
with zipfile.ZipFile(ipa) as z:    # SideStore refuses an IPA whose build number differs from the source's, so take it from the IPA itself
    plist = [n for n in z.namelist() if n.endswith(".app/Info.plist") and n.count("/") == 2][0]
    build = str(plistlib.loads(z.read(plist))["CFBundleVersion"])
entry = {"version": version, "buildVersion": build, "date": today, "downloadURL": base + os.path.basename(ipa), "size": size, "sha256": sha,
         "minOSVersion": "15.0", "localizedDescription": "Version %s." % version}
app = {"name": "Toontown: Anywhere", "bundleIdentifier": bundle, "developerName": "lPuffyy", "subtitle": "Native client for iPhone and iPad",
       "localizedDescription": "The native iPhone and iPad client for Toontown: Anywhere. It runs the same game as the website and the Windows app: "
                               "the same sign-in, settings and chat, filling the whole screen on every device.\n\nGame files download on first "
                               "launch (about 400 MB). Not affiliated with Disney.",
       "iconURL": latest + os.path.basename(icon), "tintColor": "3a8bf0", "category": "games", "versions": [entry], "version": version,
       "versionDate": today, "downloadURL": entry["downloadURL"], "size": size}
src = {"name": "Toontown: Anywhere", "identifier": "com.puffsco.toontownanywhere.source.github",
       "subtitle": "The Toontown: Anywhere client for iPhone and iPad",
       "description": "The Toontown: Anywhere app for iPhone and iPad. The game itself downloads from the Toontown: Anywhere server the first time "
                      "you play. Not affiliated with Disney.",
       "website": "https://toontown.puffsco.com/", "iconURL": latest + os.path.basename(icon), "tintColor": "3a8bf0",
       "sourceURL": latest + "altstore.json", "apps": [app],
       "news": [{"title": "Version %s" % version, "identifier": "release-%s" % version, "caption": "Version %s." % version, "date": today,
                 "tintColor": "3a8bf0", "notify": False, "appID": bundle}]}
json.dump(src, open(out, "w", encoding="utf8"), indent=2)
print("wrote", out)
