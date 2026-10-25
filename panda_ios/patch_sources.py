"""Source patches applied to the Panda3D fork before the host build (macOS-only pieces, stale iPhone display code).

  python patch_sources.py <panda3d dir>
"""
import os
import re
import sys

root = sys.argv[1]
NL = "\n"


def path(p):
    return os.path.join(root, p)


def edit(p, fn):
    with open(path(p), "r", errors="replace") as f:
        s = f.read()
    n = fn(s)
    if n != s:
        with open(path(p), "w") as f:
            f.write(n)
        print("patched", p)
    else:
        print("UNCHANGED", p)


# --- direct/showbase: Carbon / AppKit are macOS only ---
def showbase(s):
    s = re.sub(r"#ifdef __APPLE__\n// We have to include this before.*?\n#endif\n", "", s, count=1, flags=re.S)
    s = s.replace("#ifdef IS_OSX\n  activate_osx_application();", "#if defined(IS_OSX) && !defined(BUILD_IPHONE)\n  activate_osx_application();")
    return s


edit("direct/src/showbase/showBase.cxx", showbase)
edit("direct/src/showbase/showBase_assist.mm", lambda s: s.replace("#ifdef IS_OSX", "#if defined(IS_OSX) && !defined(BUILD_IPHONE)"))


# --- iphonedisplay: port the 2009 code to the 1.10 API ---
def window(s):
    s = s.replace("const string &name", "const std::string &name")
    s = s.replace(
        '  GraphicsWindowInputDevice device =' + NL +
        '    GraphicsWindowInputDevice::pointer_and_keyboard(this, "keyboard/mouse");' + NL +
        '  _input_devices.push_back(device);',
        '  PT(GraphicsWindowInputDevice) device =' + NL +
        '    GraphicsWindowInputDevice::pointer_and_keyboard(this, "keyboard_mouse");' + NL +
        '  _input_devices.push_back(device.p());' + NL +
        '  _input = std::move(device);')
    s = s.replace("_input_devices[0].", "_input->")
    s = s.replace("  _active = false;" + NL, "  set_active(false);" + NL)
    return s


edit("panda/src/iphonedisplay/iPhoneGraphicsWindow.mm", window)
edit("panda/src/iphonedisplay/iPhoneGraphicsPipe.mm", lambda s: s.replace("make_output(const string &name", "make_output(const std::string &name"))

# GL ES 1 headers: the extension header expects the Khronos 64-bit types
KH = ("#ifndef khronos_int64_t_defined" + NL + "#define khronos_int64_t_defined" + NL + "#include <stdint.h>" + NL +
      "typedef int64_t khronos_int64_t;" + NL + "typedef uint64_t khronos_uint64_t;" + NL + "#endif" + NL)
edit("panda/src/glesgsg/panda_esglext.h", lambda s: s if "khronos_int64_t_defined" in s else KH + s)

# Obj-C view header must not pull Apple's glext.h before glesgsg.h's own guard
OLD_IMPORTS = "#import <OpenGLES/ES1/gl.h>" + NL + "#import <OpenGLES/ES1/glext.h>" + NL
edit("panda/src/iphonedisplay/eaglView.h", lambda s: s.replace(OLD_IMPORTS, '#include "glesgsg.h"' + NL))


# 1.10 windows keep their own pointer/keyboard device
def win_h(s):
    s = s.replace('#include "buttonHandle.h"', '#include "buttonHandle.h"' + NL + '#include "graphicsWindowInputDevice.h"')
    return s.replace("  EAGLView *_gl_view;", "  EAGLView *_gl_view;" + NL + "  PT(GraphicsWindowInputDevice) _input;")


edit("panda/src/iphonedisplay/iPhoneGraphicsWindow.h", win_h)


# OES framebuffer entry points live in Apple's ES1 glext.h, which glesgsg.h keeps out; declare them for eaglView.mm
PROTOS = NL.join([
    'extern "C" {',
    "void glGenFramebuffersOES(GLsizei n, GLuint *framebuffers);",
    "void glGenRenderbuffersOES(GLsizei n, GLuint *renderbuffers);",
    "void glBindFramebufferOES(GLenum target, GLuint framebuffer);",
    "void glBindRenderbufferOES(GLenum target, GLuint renderbuffer);",
    "void glFramebufferRenderbufferOES(GLenum target, GLenum attachment, GLenum renderbuffertarget, GLuint renderbuffer);",
    "void glGetRenderbufferParameterivOES(GLenum target, GLenum pname, GLint *params);",
    "void glRenderbufferStorageOES(GLenum target, GLenum internalformat, GLsizei width, GLsizei height);",
    "GLenum glCheckFramebufferStatusOES(GLenum target);",
    "void glDeleteFramebuffersOES(GLsizei n, const GLuint *framebuffers);",
    "void glDeleteRenderbuffersOES(GLsizei n, const GLuint *renderbuffers);",
    "}", ""])
edit("panda/src/iphonedisplay/eaglView.mm",
     lambda s: s if "glGenFramebuffersOES(GLsizei" in s else s.replace('#include "iPhoneGraphicsWindow.h"' + NL, '#include "iPhoneGraphicsWindow.h"' + NL + PROTOS, 1))


# showBase.h still declares activate_osx_application (interrogate binds it); give iOS an empty definition
STUB = NL + "#if defined(BUILD_IPHONE)" + NL + 'extern "C++" __attribute__((visibility("default"))) void activate_osx_application() {}' + NL + "#endif" + NL
edit("direct/src/showbase/showBase_assist.mm", lambda s: s if "visibility(\"default\")) void activate_osx" in s else s + STUB)


# Apple's BGRA texture extension: external format GL_BGRA, but the *internal* format must be GL_RGBA
def gl_internal(s):
    a = "      return _supports_bgr ? GL_BGRA : GL_RGBA;" + NL + "    }" + NL + "#else"
    b = ("#ifdef BUILD_IPHONE" + NL + "      return GL_RGBA;" + NL + "#else" + NL + "      return _supports_bgr ? GL_BGRA : GL_RGBA;" + NL +
         "#endif" + NL + "    }" + NL + "#else")
    n = s.replace(a, b, 1)
    a2 = "    return _supports_bgr ? GL_BGRA : GL_RGBA8_OES;"
    b2 = "#ifdef BUILD_IPHONE" + NL + "    return GL_RGBA;" + NL + "#else" + NL + a2 + NL + "#endif"
    n = n.replace(a2, b2, 1)
    a3 = "    return _supports_bgr ? GL_BGRA : (force_sized ? GL_RGBA8 : GL_RGBA);"
    b3 = "#ifdef BUILD_IPHONE" + NL + "    return GL_RGBA;" + NL + "#else" + NL + a3 + NL + "#endif"
    return n.replace(a3, b3, 1)


edit("panda/src/glstuff/glGraphicsStateGuardian_src.cxx", gl_internal)


# this fork's MovieAudioCursor::read_samples(n, data) returns void; the OpenAL code still wants the sample count
edit("panda/src/audiotraits/openalAudioManager.cxx",
     lambda s: s.replace("    samples = stream->read_samples(samples, data);", "    stream->read_samples(samples, data);"))


# ---- retina: render at the screen's real pixel size (capped at 2x), and give Panda pixel coordinates ----
def retina_view(s):
    return s.replace("    CAEAGLLayer *eaglLayer = (CAEAGLLayer *)self.layer;",
                     "    self.contentScaleFactor = MIN([[UIScreen mainScreen] scale], 2.0);" + NL +
                     "    CAEAGLLayer *eaglLayer = (CAEAGLLayer *)self.layer;", 1)


edit("panda/src/iphonedisplay/eaglView.mm", retina_view)


def retina_window(s):
    s = s.replace("bounds.size.width, bounds.size.height", "bounds.size.width * [_gl_view contentScaleFactor], bounds.size.height * [_gl_view contentScaleFactor]")
    s = s.replace("  sum.x /= count;" + NL + "  sum.y /= count;",
                  "  sum.x = sum.x / count * [_gl_view contentScaleFactor];" + NL + "  sum.y = sum.y / count * [_gl_view contentScaleFactor];")
    return s


edit("panda/src/iphonedisplay/iPhoneGraphicsWindow.mm", retina_window)


# ---- keep the game inside the safe area (notch / rounded corners / home indicator) ----
def safe_area(s):
    old = "  iphonepipe->_view_controller.view = _gl_view;" + NL + "  [ _gl_view layoutSubviews ];"
    new = ("  {" + NL +
           "    UIEdgeInsets si = UIEdgeInsetsZero;" + NL +
           "    UIWindow *pw = iphonepipe->_window;" + NL +
           "    if ([pw respondsToSelector:@selector(safeAreaInsets)]) { si = [pw safeAreaInsets]; }" + NL +
           "    for (UIWindow *w in [[UIApplication sharedApplication] windows]) {" + NL +
           "      UIEdgeInsets e = [w safeAreaInsets];" + NL +
           "      si.left = MAX(si.left, e.left); si.right = MAX(si.right, e.right); si.bottom = MAX(si.bottom, e.bottom);" + NL +
           "    }" + NL +
           "    CGRect full = [[UIScreen mainScreen] bounds];" + NL +
           "    CGFloat inset = MAX(si.left, si.right);" + NL +
           "    UIView *container = [[UIView alloc] initWithFrame:full];" + NL +
           "    container.backgroundColor = [UIColor blackColor];" + NL +
           "    iphonepipe->_view_controller.view = container;" + NL +
           "    [iphonepipe->_window addSubview:container];" + NL +
           "    [_gl_view setFrame:CGRectMake(inset, 0, full.size.width - 2 * inset, full.size.height - si.bottom)];" + NL +
           "    [container addSubview:_gl_view];" + NL +
           "  }" + NL +
           "  [ _gl_view layoutSubviews ];")
    return s.replace(old, new, 1)


edit("panda/src/iphonedisplay/iPhoneGraphicsWindow.mm", safe_area)


# ---- iOS 27 needs the scene life cycle: the game's window has to be created inside the app's scene ----
def scene_window(s):
    old = "  _window = [ [ UIWindow alloc ] initWithFrame: screenBounds ];"
    new = ("  UIWindowScene *ttr_scene = nil;" + NL +
           "  for (UIScene *sc in [[UIApplication sharedApplication] connectedScenes]) {" + NL +
           "    if ([sc isKindOfClass:[UIWindowScene class]]) { ttr_scene = (UIWindowScene *)sc; break; }" + NL +
           "  }" + NL +
           "  if (ttr_scene) {" + NL +
           "    _window = [ [ UIWindow alloc ] initWithWindowScene: ttr_scene ];" + NL +
           "    _window.frame = screenBounds;" + NL +
           "  } else {" + NL +
           "    _window = [ [ UIWindow alloc ] initWithFrame: screenBounds ];" + NL +
           "  }")
    assert old in s, "UIWindow creation not found in iPhoneGraphicsPipe.mm"
    return s.replace(old, new, 1)


edit("panda/src/iphonedisplay/iPhoneGraphicsPipe.mm", scene_window)

