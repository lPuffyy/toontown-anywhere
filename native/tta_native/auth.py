"""The server's sign-in service: /auth (check or create an account), /setrecovery and /recover (forgot-password answers)."""
import urllib.error
import urllib.request


def _post(server, path, body, timeout=20):
    req = urllib.request.Request(server.rstrip("/") + path, data=body.encode("utf8"), method="POST",
                                 headers={"Content-Type": "text/plain", "User-Agent": "TTAnywhere-native"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf8", "replace").strip()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf8", "replace").strip()
    except Exception as e:
        return 0, "Can't reach the server (%s)." % (getattr(e, "reason", e),)


def sign_in(server, user, password):
    """-> (ok, text): on success text is 'ok' or 'setup' (the account has no recovery answers yet); otherwise a message for the player."""
    status, text = _post(server, "/auth", "%s:%s" % (user, password))
    return status == 200, text


def set_recovery(server, user, password, nickname, toon):
    status, text = _post(server, "/setrecovery", "%s:%s\n%s\n%s" % (user, password, nickname, toon))
    return status == 200, text


def recover(server, user, nickname, toon, new_password):
    status, text = _post(server, "/recover", "\n".join((user, nickname, toon, new_password)))
    return status == 200, text
