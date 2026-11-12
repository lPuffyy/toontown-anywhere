// Toontown: Anywhere for iPhone and iPad: native shell around the game client (Panda3D + embedded Python).
//  - branded loading screen with download progress
//  - starts the game, then overlays touch controls (joystick, jump)
//  - 5 taps in the top-left corner toggles the developer log overlay
#import <UIKit/UIKit.h>
#include <signal.h>
#include <execinfo.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/utsname.h>
#import <Security/Security.h>
#import <AVFoundation/AVFoundation.h>
#import <OpenAL/alc.h>
#import <QuartzCore/QuartzCore.h>
#import <CommonCrypto/CommonDigest.h>
#import <CoreText/CoreText.h>
#include <Python.h>

#import "app_config.h"   // RESOURCE_SERVER and GAME_SERVER, generated at build time

// ---------------------------------------------------------------------------------------------
// Python helpers (the main thread must not hold the GIL while idle so the download thread can run)

static void pyRun(const char *code) {
    PyGILState_STATE g = PyGILState_Ensure();
    PyRun_SimpleString(code);
    PyGILState_Release(g);
}

static NSString *pyString(const char *code, const char *var) {
    PyGILState_STATE gs = PyGILState_Ensure();
    PyRun_SimpleString(code);
    PyObject *main = PyImport_AddModule("__main__");
    PyObject *r = PyObject_GetAttrString(main, var);
    NSString *s = @"";
    if (r) {
        const char *c = PyUnicode_AsUTF8(r);
        if (c) s = [NSString stringWithUTF8String:c];
        Py_DECREF(r);
    } else {
        PyErr_Clear();
    }
    PyGILState_Release(gs);
    return s;
}

// ----- crash reporting ----------------------------------------------------------------------------------------------------------
// The game's output goes to <docs>/tta_log.txt once a game starts. A crash writes what it was (signal and backtrace) at the end of that file, and a
// marker file says a game start never finished. On the next start the app sends the end of the previous log to the server (client.log, "IOSAPP|"),
// so a crash on a phone can be read there. Nothing is sent when the last run was fine.
static int gCrashFd = -1;
static char gMarkerPath[1024];
static char gPrevLogPath[1024];
static BOOL gSendPrevLog = NO;
static BOOL gHavePrevLog = NO;

static void CrashWrite(const char *s) {
    if (gCrashFd >= 0 && s) { ssize_t r = write(gCrashFd, s, strlen(s)); (void)r; }
}

static void CrashSignal(int sig) {
    const char *name = sig == SIGSEGV ? "SIGSEGV" : sig == SIGBUS ? "SIGBUS" : sig == SIGABRT ? "SIGABRT" : sig == SIGILL ? "SIGILL" :
                       sig == SIGFPE ? "SIGFPE" : sig == SIGTRAP ? "SIGTRAP" : "signal";
    CrashWrite("\nNATIVE CRASH: ");
    CrashWrite(name);
    CrashWrite("\n");
    void *frames[48];
    int n = backtrace(frames, 48);
    if (gCrashFd >= 0) backtrace_symbols_fd(frames, n, gCrashFd);
    signal(sig, SIG_DFL);
    raise(sig);
}

static void CrashException(NSException *e) {
    NSString *t = [NSString stringWithFormat:@"\nNATIVE CRASH: uncaught exception %@: %@\n%@\n", e.name, e.reason, [e.callStackSymbols componentsJoinedByString:@"\n"]];
    CrashWrite(t.UTF8String);
}

static void CrashMarkerSet(void) {
    int fd = open(gMarkerPath, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0) { const char *t = "launching\n"; ssize_t r = write(fd, t, strlen(t)); (void)r; close(fd); }
}

static void CrashMarkerClear(void) {
    unlink(gMarkerPath);
}

static void InstallCrashHandlers(void) {
    NSString *docs = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
    if (!docs) return;
    NSString *log = [docs stringByAppendingPathComponent:@"tta_log.txt"];
    NSString *prev = [docs stringByAppendingPathComponent:@"tta_log.prev.txt"];
    NSString *marker = [docs stringByAppendingPathComponent:@"tta_launching"];
    strlcpy(gMarkerPath, marker.UTF8String, sizeof gMarkerPath);
    strlcpy(gPrevLogPath, prev.UTF8String, sizeof gPrevLogPath);
    NSFileManager *fm = [NSFileManager defaultManager];
    BOOL unfinished = [fm fileExistsAtPath:marker];
    NSData *d = [NSData dataWithContentsOfFile:log];
    BOOL crashed = d.length > 0 && [d rangeOfData:[@"NATIVE CRASH" dataUsingEncoding:NSUTF8StringEncoding] options:0 range:NSMakeRange(0, d.length)].location != NSNotFound;
    // a crash inside the sound code turns the game's sound off on this phone (the same app version keeps it off; a new version tries again)
    NSString *noaudio = [docs stringByAppendingPathComponent:@"tta_noaudio"];
    NSString *appVer = [[NSBundle mainBundle] objectForInfoDictionaryKey:@"CFBundleShortVersionString"] ?: @"?";
    NSString *savedVer = [NSString stringWithContentsOfFile:noaudio encoding:NSUTF8StringEncoding error:nil];
    if (savedVer && ![savedVer isEqualToString:appVer]) { [fm removeItemAtPath:noaudio error:nil]; }
    if (crashed && [d rangeOfData:[@"libp3openal_audio" dataUsingEncoding:NSUTF8StringEncoding] options:0 range:NSMakeRange(0, d.length)].location != NSNotFound) {
        [appVer writeToFile:noaudio atomically:YES encoding:NSUTF8StringEncoding error:nil];
    }
    if ([fm fileExistsAtPath:noaudio]) setenv("TTA_NOAUDIO", "1", 1);
    [fm removeItemAtPath:prev error:nil];
    if (d.length > 0) [fm moveItemAtPath:log toPath:prev error:nil];      // each run starts a fresh log; the last one is kept for the report
    gHavePrevLog = [fm fileExistsAtPath:prev];
    gSendPrevLog = (unfinished || crashed) && gHavePrevLog;
    [fm removeItemAtPath:marker error:nil];
    gCrashFd = open(log.UTF8String, O_WRONLY | O_CREAT | O_APPEND, 0644);
    struct utsname u;
    uname(&u);
    NSString *head = [NSString stringWithFormat:@"RUN START ios %@ model %s app %@\n", [[UIDevice currentDevice] systemVersion], u.machine,
                      [[NSBundle mainBundle] objectForInfoDictionaryKey:@"CFBundleShortVersionString"] ?: @"?"];
    CrashWrite(head.UTF8String);
    int sigs[] = {SIGSEGV, SIGBUS, SIGABRT, SIGILL, SIGFPE, SIGTRAP};
    for (size_t i = 0; i < sizeof sigs / sizeof sigs[0]; i++) signal(sigs[i], CrashSignal);
    NSSetUncaughtExceptionHandler(CrashException);
}

static CGFloat UIScale(void) {
    return UI_USER_INTERFACE_IDIOM() == UIUserInterfaceIdiomPad ? 1.45 : 1.0;
}

// The game's lettering (Toon Display), the same font the web app uses. It is downloaded from the server into <data>/ui with the start-screen
// pictures, registered for this app, and used everywhere the old Marker Felt was; Marker Felt stays as the fallback until it is there.
static NSString *gToonFontName = nil;
static NSString *gToonFontPath = nil;

// The cloud sky, the lettering font and the logo are built into the app (ui_bundled), so the very first start already looks right; a newer copy
// downloaded from the server into <data>/ui is used when there is one.
static NSString *UIFilePath(NSString *dataPath, NSString *name) {
    NSString *p = [[dataPath stringByAppendingPathComponent:@"ui"] stringByAppendingPathComponent:name];
    if ([[NSFileManager defaultManager] fileExistsAtPath:p]) return p;
    p = [[[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"ui_bundled"] stringByAppendingPathComponent:name];
    return [[NSFileManager defaultManager] fileExistsAtPath:p] ? p : nil;
}

static void RegisterToonFont(NSString *dataPath) {
    NSString *p = UIFilePath(dataPath, @"ToonDisplay.ttf");
    if (!p || [gToonFontPath isEqualToString:p]) return;
    NSURL *u = [NSURL fileURLWithPath:p];
    CFErrorRef err = NULL;
    CTFontManagerRegisterFontsForURL((__bridge CFURLRef)u, kCTFontManagerScopeProcess, &err);     // fails harmlessly if it is already registered
    if (err) CFRelease(err);
    CFArrayRef ds = CTFontManagerCreateFontDescriptorsFromURL((__bridge CFURLRef)u);
    if (ds) {
        if (CFArrayGetCount(ds) > 0) {
            CTFontDescriptorRef d = (CTFontDescriptorRef)CFArrayGetValueAtIndex(ds, 0);
            CFStringRef name = (CFStringRef)CTFontDescriptorCopyAttribute(d, kCTFontNameAttribute);
            if (name) {
                gToonFontName = [(__bridge NSString *)name copy];
                CFRelease(name);
            }
        }
        CFRelease(ds);
    }
    gToonFontPath = p;
}

static UIFont *ToonFont(CGFloat size) {
    UIFont *f = gToonFontName ? [UIFont fontWithName:gToonFontName size:size] : nil;
    if (!f) f = [UIFont fontWithName:@"MarkerFelt-Wide" size:size];
    return f ?: [UIFont boldSystemFontOfSize:size];
}

// Letters with a solid outline, like the web app's title and loading text.
static NSAttributedString *Outlined(NSString *text, UIFont *font, UIColor *fill, UIColor *outline, CGFloat width) {
    return [[NSAttributedString alloc] initWithString:text attributes:@{NSFontAttributeName: font, NSForegroundColorAttributeName: fill,
                                                                         NSStrokeColorAttributeName: outline, NSStrokeWidthAttributeName: @(-width)}];
}

// A view controller that says when its view's size changes (a rotation, a foldable opening or closing).
@interface TTAViewController : UIViewController
@property (copy, nonatomic) void (^onLayout)(CGSize size);
@end
@implementation TTAViewController
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    if (self.onLayout) self.onLayout(self.view.bounds.size);
}
@end

// ---------------------------------------------------------------------------------------------
// Touch controls

@interface PassThroughWindow : UIWindow
@end
@implementation PassThroughWindow
- (UIView *)hitTest:(CGPoint)point withEvent:(UIEvent *)event {
    UIView *v = [super hitTest:point withEvent:event];
    return (v == self || v == self.rootViewController.view) ? nil : v;
}
@end

// The app's window scene (UIKit requires the scene lifecycle for apps built with the iOS 27 SDK). Every window is made in it, and the screen's
// size is the scene's, not UIScreen's: on a two-screen phone (iPhone Duo) they are not the same thing.
static UIWindowScene *gScene = nil;

// The safe area plus a margin on the right for near-square iPhone windows (the iPhone Duo's inner screen): the system bar down its right side
// swallows taps there, and it is not part of the safe area, so the game's right-hand buttons (friends list, sticker book) did nothing.
static UIEdgeInsets TTAInsets(UIEdgeInsets s, CGRect b) {
    if (UI_USER_INTERFACE_IDIOM() == UIUserInterfaceIdiomPhone && b.size.height > 0 && b.size.width / b.size.height < 1.9) {
        s.right = MAX(s.right, MAX(44.0, b.size.width * 0.065));
    }
    // Two-screen phone in full-display mode: the earlier (compatibility mode) builds put the whole game inside a window as wide as the main screen,
    // centred on the big one, and everything worked there. The strip beyond it on the right (the system bar and its margin) does not take taps even
    // though the safe area only says 84 points, so the game's buttons are kept inside that same width.
    if (gScene != nil && gScene.screen.bounds.size.width > [UIScreen mainScreen].bounds.size.width + 1.0) {
        CGFloat gap = (gScene.screen.bounds.size.width - [UIScreen mainScreen].bounds.size.width) / 2.0 + 8.0;
        if (gap > 0) s.right = MAX(s.right, gap);
    }
    return s;
}

// The view controller of the app's windows. On a two-screen phone in full-display mode iOS watches the right edge for a swipe that reveals a side
// bar, and holds back or swallows taps there (the game's buttons at the right edge did nothing); asking iOS to defer its edge gestures on that side
// gives the app the touches first.
@interface TTAEdgeViewController : UIViewController
@end
@implementation TTAEdgeViewController
- (UIRectEdge)preferredScreenEdgesDeferringSystemGestures {
    if (gScene != nil && gScene.screen.bounds.size.width > [UIScreen mainScreen].bounds.size.width + 1.0) return UIRectEdgeRight;
    return UIRectEdgeNone;
}
@end
static CGRect SceneBounds(void) {
    if (gScene) { CGRect r = gScene.coordinateSpace.bounds; if (r.size.width > 0) return r; }
    return [UIScreen mainScreen].bounds;
}
static __kindof UIWindow *NewWindow(Class cls, CGRect frame) {
    UIWindow *w = gScene ? [[cls alloc] initWithWindowScene:gScene] : [[cls alloc] initWithFrame:frame];
    w.frame = frame;
    return w;
}
@interface JoystickView : UIView
@property (strong, nonatomic) UIView *knob;
@property (assign, nonatomic) int fwd, back, left, right;
@end

@implementation JoystickView
- (instancetype)initWithFrame:(CGRect)frame {
    if ((self = [super initWithFrame:frame])) {
        self.backgroundColor = [UIColor colorWithWhite:1 alpha:0.14];
        self.layer.cornerRadius = frame.size.width / 2;
        self.layer.borderWidth = 3;
        self.layer.borderColor = [UIColor colorWithWhite:1 alpha:0.45].CGColor;
        CGFloat k = frame.size.width * 0.42;
        self.knob = [[UIView alloc] initWithFrame:CGRectMake(0, 0, k, k)];
        self.knob.center = CGPointMake(frame.size.width / 2, frame.size.height / 2);
        self.knob.backgroundColor = [UIColor colorWithRed:1.0 green:0.82 blue:0.2 alpha:0.85];
        self.knob.layer.cornerRadius = k / 2;
        self.knob.layer.borderWidth = 3;
        self.knob.layer.borderColor = [UIColor colorWithWhite:0 alpha:0.35].CGColor;
        self.knob.userInteractionEnabled = NO;
        [self addSubview:self.knob];
    }
    return self;
}
- (void)update:(UITouch *)t {
    CGPoint p = [t locationInView:self];
    CGFloat cx = self.bounds.size.width / 2, cy = self.bounds.size.height / 2;
    CGFloat dx = p.x - cx, dy = p.y - cy;
    CGFloat maxr = self.bounds.size.width * 0.38;
    CGFloat len = sqrt(dx * dx + dy * dy);
    if (len > maxr) { dx = dx / len * maxr; dy = dy / len * maxr; }
    self.knob.center = CGPointMake(cx + dx, cy + dy);
    CGFloat nx = dx / maxr, ny = -dy / maxr;               // up is forward
    int f = ny > 0.35, b = ny < -0.35, l = nx < -0.35, r = nx > 0.35;
    if (f != self.fwd || b != self.back || l != self.left || r != self.right) {
        self.fwd = f; self.back = b; self.left = l; self.right = r;
        [self send];
    }
}
- (void)send {
    NSString *code = [NSString stringWithFormat:@"import ios_game\nios_game.ui_move(%d,%d,%d,%d)\n", self.fwd, self.back, self.left, self.right];
    pyRun(code.UTF8String);
}
- (void)touchesBegan:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { [self update:touches.anyObject]; }
- (void)touchesMoved:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { [self update:touches.anyObject]; }
- (void)reset {
    self.knob.center = CGPointMake(self.bounds.size.width / 2, self.bounds.size.height / 2);
    self.fwd = self.back = self.left = self.right = 0;
    [self send];
}
- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { [self reset]; }
- (void)touchesCancelled:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { [self reset]; }
@end

@interface PadButton : UIView
@property (copy, nonatomic) NSString *kind;     // "camera" or "action"
@end
@implementation PadButton
- (instancetype)initWithFrame:(CGRect)frame kind:(NSString *)kind title:(NSString *)title {
    if ((self = [super initWithFrame:frame])) {
        self.kind = kind;
        self.backgroundColor = [UIColor colorWithRed:0.95 green:0.55 blue:0.15 alpha:0.6];
        self.layer.cornerRadius = frame.size.width / 2;
        self.layer.borderWidth = 3;
        self.layer.borderColor = [UIColor colorWithWhite:1 alpha:0.6].CGColor;
        UILabel *l = [[UILabel alloc] initWithFrame:self.bounds];
        l.text = title;
        l.textAlignment = NSTextAlignmentCenter;
        l.textColor = [UIColor whiteColor];
        l.adjustsFontSizeToFitWidth = YES;
        l.minimumScaleFactor = 0.5;
        l.font = ToonFont(frame.size.width * 0.26);
        [self addSubview:l];
    }
    return self;
}
- (void)setDown:(BOOL)d {
    self.alpha = d ? 0.7 : 1.0;
    if ([self.kind isEqualToString:@"action"]) {
        NSString *code = [NSString stringWithFormat:@"import ios_game\nios_game.ui_action(%d)\n", d ? 1 : 0];
        pyRun(code.UTF8String);
    } else if ([self.kind isEqualToString:@"padleft"] || [self.kind isEqualToString:@"padright"]) {
        NSString *code = [NSString stringWithFormat:@"import ios_game\nios_game.ui_pad(%d, %d)\n", [self.kind isEqualToString:@"padright"] ? 1 : 0, d ? 1 : 0];
        pyRun(code.UTF8String);
    } else if (d) {
        pyRun("import ios_game\nios_game.ui_camera()\n");
    }
}
- (void)touchesBegan:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { [self setDown:YES]; }
- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { [self setDown:NO]; }
- (void)touchesCancelled:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { [self setDown:NO]; }
@end

@interface JumpButton : UIView
@end
@implementation JumpButton
- (instancetype)initWithFrame:(CGRect)frame {
    if ((self = [super initWithFrame:frame])) {
        self.backgroundColor = [UIColor colorWithRed:0.25 green:0.6 blue:1.0 alpha:0.55];
        self.layer.cornerRadius = frame.size.width / 2;
        self.layer.borderWidth = 3;
        self.layer.borderColor = [UIColor colorWithWhite:1 alpha:0.6].CGColor;
        UILabel *l = [[UILabel alloc] initWithFrame:self.bounds];
        l.text = @"JUMP";
        l.textAlignment = NSTextAlignmentCenter;
        l.textColor = [UIColor whiteColor];
        l.font = ToonFont(20);
        [self addSubview:l];
    }
    return self;
}
- (void)setDown:(BOOL)d {
    self.alpha = d ? 0.7 : 1.0;
    NSString *code = [NSString stringWithFormat:@"import ios_game\nios_game.ui_jump(%d)\n", d ? 1 : 0];
    pyRun(code.UTF8String);
}
- (void)touchesBegan:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { [self setDown:YES]; }
- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { [self setDown:NO]; }
- (void)touchesCancelled:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event { [self setDown:NO]; }
@end

// ---------------------------------------------------------------------------------------------

@interface SceneDelegate : UIResponder <UIWindowSceneDelegate>
@property (strong, nonatomic) UIWindow *window;
@end

// Logs where the first touches land as iOS delivers them (before any window or view of ours sees them), so a screen where taps do not reach
// the game shows up as touches that never arrive, or arrive somewhere else.
@interface TTAApplication : UIApplication
@end
@implementation TTAApplication
- (void)sendEvent:(UIEvent *)event {
    static int count = 0;
    if (event.type == UIEventTypeTouches && count < 150) {
        for (UITouch *t in event.allTouches) {
            if (t.phase != UITouchPhaseBegan) continue;
            CGPoint p = [t locationInView:nil];
            UIWindow *w = t.window;
            fprintf(stderr, "UITOUCH %d at (%.0f, %.0f) of a %.0fx%.0f window, window=%s view=%s\n", ++count, p.x, p.y, w.bounds.size.width, w.bounds.size.height,
                    NSStringFromClass([w class]).UTF8String, NSStringFromClass([t.view class]).UTF8String);
        }
    }
    [super sendEvent:event];
}
@end

@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property (strong, nonatomic) UIWindow *window;
@property (strong, nonatomic) CADisplayLink *link;
// screen size and safe area, as last told to the game (a rotation, a foldable opening or closing and Stage Manager all change them)
@property (copy, nonatomic) NSString *lastMetrics;
@property (strong, nonatomic) UIWindow *settingsWindow;
@property (assign, nonatomic) CGSize lastLoginSize;
@property (copy, nonatomic) NSString *settingsNote;
@property (assign, nonatomic) NSUInteger frameTick;
@property (strong, nonatomic) NSTimer *poll;
// loading screen
@property (strong, nonatomic) UILabel *statusLabel;
@property (strong, nonatomic) UILabel *detailLabel;
@property (strong, nonatomic) UIProgressView *bar;
@property (strong, nonatomic) UIActivityIndicatorView *spinner;
@property (strong, nonatomic) UITextView *errorView;
@property (copy, nonatomic) NSString *report;
// start-screen art and sign-in
@property (strong, nonatomic) UIImageView *bgView;
@property (strong, nonatomic) UIImageView *logoView;
@property (strong, nonatomic) CAGradientLayer *gradient;
@property (strong, nonatomic) NSArray<UIView *> *fallbackViews;
@property (strong, nonatomic) UIView *loginView;
@property (strong, nonatomic) UIWindow *loginWindow;
@property (strong, nonatomic) UITextField *userField;
@property (strong, nonatomic) UITextField *passField;
@property (strong, nonatomic) UILabel *loginError;
@property (strong, nonatomic) UIButton *playButton;
// server choice
@property (copy, nonatomic) NSString *serverRes;
@property (copy, nonatomic) NSString *serverGame;
@property (assign, nonatomic) BOOL serverIsDefault;
@property (strong, nonatomic) UIWindow *serverWindow;
@property (strong, nonatomic) UIScrollView *serverScroll;
@property (strong, nonatomic) UITextField *resField;
@property (strong, nonatomic) UITextField *gameField;
@property (strong, nonatomic) UILabel *serverMsg;
@property (strong, nonatomic) UIButton *connectBtn;
@property (strong, nonatomic) UIButton *defaultBtn;
@property (strong, nonatomic) UIButton *changeServerBtn;
// password-recovery card
@property (strong, nonatomic) UIWindow *recWindow;
@property (strong, nonatomic) UIScrollView *recScroll;
@property (strong, nonatomic) UITextField *recNick;
@property (strong, nonatomic) UITextField *recToon;
@property (strong, nonatomic) UITextField *recPw;
@property (strong, nonatomic) UILabel *recMsg;
@property (strong, nonatomic) UIButton *recPrimary;
@property (strong, nonatomic) UIButton *recSecondary;
@property (assign, nonatomic) BOOL recReset;
@property (copy, nonatomic) NSString *recCookie;
@property (copy, nonatomic) NSString *recUser;
@property (copy, nonatomic) void (^recDone)(void);
// in-game touch helpers
@property (strong, nonatomic) PadButton *actionButton;
@property (strong, nonatomic) NSArray<UIView *> *hudViews;
@property (strong, nonatomic) NSArray<UIButton *> *hotButtons;     // friends list and sticker book, pressed natively on a two-screen phone
@property (assign, nonatomic) BOOL hotspots;
@property (strong, nonatomic) JoystickView *joyView;
@property (assign, nonatomic) BOOL hudWasVisible;
@property (strong, nonatomic) PadButton *padLeft;
@property (strong, nonatomic) PadButton *padRight;
@property (assign, nonatomic) ALCcontext *alContext;
@property (strong, nonatomic) UITextField *kbField;
@property (assign, nonatomic) BOOL kbActive;
@property (strong, nonatomic) NSTimer *uiPoll;
// overlays
@property (strong, nonatomic) PassThroughWindow *controls;
@property (strong, nonatomic) UIWindow *logWindow;
@property (strong, nonatomic) UITextView *logView;
@property (strong, nonatomic) NSTimer *logTimer;
@end

// ---------------------------------------------------------------------------------------------
// Community links on the sign-in screen (small white-on-transparent logos, embedded so no files are needed)
static NSString *const kDiscordURL = @"https://discord.gg/NxdkuR2aCp";
static NSString *const kRedditURL = @"https://www.reddit.com/r/ToontownAnywhere/s/p7FFnl9jGJ";
static NSString *const kDiscordIcon = @"iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAYAAADimHc4AAAID0lEQVR4Aeydi3nUOBSFRzQCVLKkkiWVECqBrSTZSkgn5vyKZfyU9RwNE+XTjTyydB/n3CvPOB74cOk/TRHoBDSF/3LpBHQCGiPQ2HyvgE5AYwQam+8V0AlojEBj870COgGNEWhs/n1WQGPQ5+ZvgoBhGL4ic8dqHmNrlE817YTovjoBCvyLBMB/qP8lGeToD0TH1QEZbVh7sol95Fnj3yTV7cvmolUnQEEBNgLggP0sDwDgq/p1wP9qrHZb28CHLzL6JIEMuTw4QhjXcL1WjYBhGMioX3IdsBEA10tvexqGAUC8k1JPjroB+kwFwDPvWWsQYqniV1EC5CyZjsODIiSAFKfXGSpV2yZbnyRsZwjHIbaCdK+sOTKoDmKz9lZzkl9mEzCC4LYXMh2Hkx3SQqqAjEPQixA4ACAyOUAw1cV2hnDsztEjrEFYj65v6JbkNGKz9uQEekNI99pLJkAOkAkEjkMh24vXkdVJqgdBL0LgBIuspm5eMgdhDcJ6dCGbyRkD6HVEYydJVRIBAp8AAZ4+yfAdLQL85GpIIkDgpeylWna3jURMwiSagDH7S5fzPTDzNGITFUs0AdLOhVZdbHsX87noUw3BwUYRIIZ5J8GeF2zgnU0E/KitKJgAgY/yvvWcZ1TUVhRMgOxGMav577kFYxVEQM/+6FwKroIgAmQ+mFHN7e0NAa6Xb0ee36cE9Oz3oOc/xX0xrpveWacEaHXPfoGQ2E6rwEtAz/5E2P8sO60CLwHS07NfIGQ2bxUcEtCzPxP2cbk6bxUcEqCFPfsFQqF2iKWPgP6ptxD6UnP4uWCXAG0//LFB63oriMDuPbRdAmT0H0lvZRHY3YY2BCj7+fDQK6As+GjjT7hgy/EkGwJ0ZpcpjfeWj8AG2z0C+sU3H+gjDZvrwIKAcfs5WtzH8xHYbEMLAqR/UyIa660sAguM1wRsSqSs7a5NCCwwnggYt5/FSU2u0V6l9KfkUfLZ6Ef9g4Rrz4v6/ObXgI3JvqZ+ljj7+KaXVdtiG5oIkMnNWySNlW4vwhvQH9X/lNiA1TP+XX1tIJ6wIZns6/hV4uxDBuSUjnutb0r0OQG1P3w9KFAAXjuzeK053zVAdVhydFyqYR/dXn2yj22ktP253QnrOQFsAfNJJY/JPEo/SKdAYG7JTIy1j20kyN+ESdNuYwkY9/8EPUFLKPHTzFtrEgmsKZGFre2vQ+P1dB2wBGhkYkTHpVtOJrFl5ZLAdpIaU87aM5sWc0fAtCedrYo9P2Zy7DI7X2tzwSf72c6svthfss/aXB+OzC4IsC+OZmaMl3AeEFJdKGG/hI49/+0HMlcBtQjIAc85/b87SOhL2K9FgMX8w3gBnt6XJgTpW1LLeZ/N0udyEsDni/1em6sA38Scc5blHAVa+1HSslW1DwElQLpcLrsY1dS9a3A1WMJ+rd0BVz/VJqCE8zk6ctYCEFJCB3r2xBJQtcTGa8ye8dOxcW0OAHafPTV0MGG0f3C2yPBHKqCIJo+SnK802bdqHt0hp3J05Pge4putgJwMCzHCx27v43l7SsbsK3F/imdyomOUfdYge+6VGrMElFLm0+N9PG+9UMFz8SyZfVHf461gfx3i9JotiGCngUoH2OBb5aePuyh4so5v4NOXcifFPmtK2T/UAwGHJyucIBMRtqVFgAKeKmGr4hv4FUxbldhGWtm3Tsx+XW0Lmtm8UAWATEXwvVp6/vENtpwSe/7l5Ke1/YV7166AhXG9YJtZVILGrtla27f/eHdLAK4JdhVbmUqbbEGZPt/X8tZb0H2hGR/NKwTcwy3j+NBvZAUE3Igr79ONTkBb3vsW1Bb/6/wfMn/7Naam/1UrgOctjX543pLna2oGUjqR+WM+z4/KfYP/Oc82eX3jGgAwiHdiwkmebLPLjDE8iEsgPGhFMDXsWVuZv/CNZ0gRjp26Wn+Y/++DwAGoGhnKfR6Em2z207ZsURVk1i2RAdD4JPcMPdlvgR9vEHJnlvtUdqzQL2zwlPgLFXAxxgAMoHAzrGR2cq8F57kDORFBEKPNR/XYpTKwjWPn9lGQLhZwLQcAmTf4wJiG3toKeJs8b2eK/OZBYSrMxmkJcGqNMbWqwRGxqIiZXRLAfj/AGAMhiCNlTox12q076JmDQCbAUt3IAnBjDHMWKgQ8/8Sxy/jSwOPPg+yC8WR3QQCjmgAYAEDgGyeZkyEERUVw3/9QjXywz3SqhxQExwEQ0bAxWoyPk5g/P8xBWGOzW6e4BnljEfjcIidmfJT6os1lPSQsFG8IcGflNEyRhWSR13m3JqJHd8T07VT5B0mTbGdEj1AlpeOEeLlqDuM9JAD3jcpUgmPIhj3mJAjZUDrQBDeWSxQnPpFsyxNpr9BDFYKbV4OXALdSzrEtUQ0IjrpTsT0Ze5gNscpKz1ec+JYTH0nqtr4gPUEEuEDlIESw70IExoKMuPXqTzNCc1o3sjfWB9YAPAIuweujCHBaRyIgAUAxHkIE5EU55+xds1dsVEGon8RutxqtC12zCCeJAKcBoxLeaVAVvIM4IoKtB8Lc0lvvSayjWACamBW6oT+aFxRjFgFzC8YY3i5CBECvySBT5tNv+tjozYccXPvMa7L9Qec51pT8VowA54qcY6tZkKExytpN+Sv60WcSCcD10mRn+17gEQTsLfePGWMsGf5Zt3tW/pNIbDnVnKxKQDWv70hxJ6AxmZ2ATkBjBBqb7xXQCWiMQGPzvQI6AY0RaGy+V0AnoDECJ+Zrn/4NAAD//6eyVawAAAAGSURBVAMASCXi36xgwZwAAAAASUVORK5CYII=";
static NSString *const kRedditIcon = @"iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAYAAADimHc4AAAJl0lEQVR4AeydSagl1RnHXyfprBPjQgk4RNFNjDYhkLYXmdCWRBeaaBYJDlFRIyaNAc2wMG4MipLBNoqaOJCA4IQjTjgsHMB52CjOICo4LHRlK8/frz31qFvTrTpV9eoOJd/fc+qcbzrfv6puvaq6t7+0Mv43aAVGAgYt/8rKSMBIwMAVGDj8eASMBAxcgYHDj0fASMCwFVhdXd0MLgUvgh0B9h3b3Hd2S30EUOxLKfAj4FSwH/hKgH3HHgk6DPcjS0sAhb2Lklpkmko5NehWKsVOLiUBq6ur7vlbGxRtKyRo08CknurSEUAhPa/X2fOzFfRI0DY73mp76QigWseCWGljWxhzaQhgz98LnEMVTgSx8uNYwzK7pSAgFP41ivBXsBHEyrdiDcvsFpoACu9e/wCLt/A0sycLSwDF/yHldq+3pduJvNqJl5SThSSA4u/FGt3zaTqV+zv1hrOFI6BG8f/DumPl2ljDMruFI4CFXgU8Amgm5HW2frRhw4aTaC8DTeUybB9tajRNf6EIYO/3fC+y636d4u0NHnSC9jTau0FduTvY1NWvrbeOBNTOqY2i1/lF9idkBynoYYzVORLc89VFvXtZGALY+4+nPEV7/wkUe+eez/yEMO6RcDCDEvES7acB9h07OOgw3I8sDAGU5wcgK556rs4Oprcp8KPgNLA/2Bhg37HOz/np2PYXiQCPANeURu7Uk56chf5CEBBOP7l6sjcXnnpyigMOLAQB1O84kJXKU09WeajtRSGg6MP33KGK2iTu3BNQcfrxD68mtRhEd+4JoGp7gqzMxenHpBeBgKLbDg+5uHnAIhBQdP6fmaufaTvBIhCQOwK4/JyL87/kzDUBfADnis+i5qb45Nr8+wEs+nhwA3gDfBpg37Giv0aN0xfW/fTDejtdf+0jIAR+g0p6v/3ntHuALwfYd+wq9CSjNRH42Q0cCraB7eBW8ARYE2KbC82EHIHCbUAbbX2parcJjYgN/Fn4ztdfiwCC/4ucXayFplsp6kiENpWK6Uli+AD9JNr/gQ+Zext4z/7vtKeDI8B3wTT5BgqHA2209RXEt/UJ9G2MolMXJsWCnWvpZf1TCQjBzyhOrXL0jGBbqsT8PuBP4FmUfIB+Be2vwNdA16JPfRvjNWMCY+9TFQgdi9/L+o1bSQDBPZXEBNe3kAR92F8Dfo8EtzPwMjgPfAestxjT2C+bCzgymwBj5t75+tNxKglAsYv7KWs+WNCx4Gn83gR+BmZFzOUmcwPp1w/Xcm+RaKWPUgJIRPY9n7eIvdN0D3xdCHy4cQ0jB4FZFXO7xlzBhSTZ1fqtJe7yUkoAqn6Q0XQif8DL98G8iLmac1f5ltayioDvdRV93f3MXsDSWlYR8M3ZW8fcZlRayyoC5na185R4FQFvzdNCZjzX0lpWEfD4jC9qntIrrWUVAf6hNE+LnOVcS2tZSgD31H2s9+Ysr2pOcnsz1LIw3VICgnbZu5ZhupNGks/G0wHgqwH2HXOOoVaiD33psw//05KrrGElAYG5i6dFaDF/Jbb7EucC8ALYEWD/AueAOjRRom2f/qcldTHr8UxSqldJgFY4+B1tHyRcie+TwQ78F4pz4GQmLSRNI+nb/7RkLL61q9SbSoDWFEFHvmfp4exQW+jntw2cqKtNXRN1tamrr642dfWr9PTjG9nWrEpv51wtAtSEhKuB7+BIxI2MvQ9S0qh7Cb5K9/ysp6B7SXa8Yrtv/9nQ1sKaWPg9ybfytJM2rk1AYqRz8Au2bwaxcmeEYRObJrpJKjE2ie3N1gTULnxi2JiAxJB2E4iVFyMMm9g00U1SibFJbKNr0YaAOs9nkwQXvY2uRRsC2hR1/wjjJjZNdJNUYmwS2+h2KAJ+GpFxE5smukkqMTaJbXQ7FAGn88iv9o9mBF1fM6m70L79181jql4bAp6c6r1cwWet/y6fzs2oq01uomRAXW1KpnPD6mqTm6g5EF2LNgT4dkPN/ArVfEHqirB3Fyo4B3yPx2+3F+pUDPbtPx06uhZtCOjiFXAL63s5Z1Hob4ONAfbPYoW+N6QO3SjRtk//SVLRtWhDwC1E/wy0FQ/983HyPPgkwL5jzjHUSvShL3127p/M/HK3taDbXKIJ4K++jwnn+5I0Sy3eorEWUUWIJiBE6+MuaXA9N02rGrQigKPgOcq0HSyrbA81iF5/KwJC1D/TvguWTVyza2+17tYEsAd8RAY+NKGJllewXAXrJcYyZpt4Pkxy7W18NP+KUlE0SLiNcZ+70jQSv4ixBft9sdoV6IemVzHGriHmFiKZA00jORt7/TQyKlJufQQkTknIZ7he7iVDddqLsPPXy1doP8BgG2i9V+GjTPS9LcQyprEvKlMuGT8fe9daMt1suDMCDEtif6T1Sw80tcSCrCli789Ctvll2zVfJZ0TQ4z09EQO6YmC/nnYu8aCqbihTgkwBRL8C+3vQR3JvTeP/fUYngK6llOC76zfXA5ZhbDtkePawmY3TecEmBYL9XtVh9Kf9p3dTdx6yJ0CsL8c22NAk70T9ULRxzHB54RCiD3taZZr2Ir9PyeMO9rohQBzI+F7aX0ZatorJWdSiNxVFPYeCX5j5Qb8TEr9LW0PCr4mrELMMycG8xvmfgD29+SnuhnpjQDTI/GPgcX1Vwcfc6wEl1OQX2bnsH0VHM34IcBi0tQSdQ/RFvi5MmEUYnmUTYynNsz1MGy91Iy+zZDyV9rtlYAkKgvxdzf9xw/8ZatnkvFMex2FkazM8IpXK/fhQyJ2WVlZ8dTkVYhF9qeEhX3HnNtFXXAfujkJMa7LTXwxYG7HYbsZ+B3lL0Z7/P+6EJDkz6KuBZ5zj2LsDpAVj4TcZ0KihO2H4HrgdfjRtD8JsO+Yc6XX9RRf30V7vrkcha9NoPOfJ07yL2rXlYAkARbpezR+cc0/wPxz3ntKybSfCU9RrM6e0eoLPEWA9DnfmMb23dHDzYn5dZdBCEhWyaJfAX8DBzK2N/AU9H9a+3dQtNtBNBHaAt/Ndw/Xp76N4c8YH0hcY7e9JUG68TIoAem0KYY/suoLtb+m/3Xmdgfe6t2PIp4DfgO2AG9ZMJUX54A66vpauP8emJfEu+sT6NsYXlrmHQwwMjMEZNdOsd4Bfnj/g/Zc8F/wMHgvq5tsOwfUUVcbbe9h7J1EZ9bamSVg1grVVz4jAX1VtqbfkYCahepLrQEBfaWw3H5HAgbmfyRgJGDgCgwcfjwCRgIGrsDA4ccjYCRg4AoMHH48AkYCBq7AwOHHI2AKAX1Pfw4AAP//UNhyIgAAAAZJREFUAwB/RE7u2+VTTAAAAABJRU5ErkJggg==";

static UIImage *LinkIcon(NSString *b64, CGFloat height) {
    NSData *d = [[NSData alloc] initWithBase64EncodedString:b64 options:0];
    UIImage *i = d ? [UIImage imageWithData:d] : nil;
    if (!i) return nil;
    CGSize s = CGSizeMake(height * i.size.width / i.size.height, height);
    return [[[UIGraphicsImageRenderer alloc] initWithSize:s] imageWithActions:^(UIGraphicsImageRendererContext *c) {
        [i drawInRect:CGRectMake(0, 0, s.width, s.height)];
    }];
}

@implementation AppDelegate

- (NSString *)resPath { return [[NSBundle mainBundle] resourcePath]; }
- (NSString *)fwPath { return [[self resPath] stringByAppendingPathComponent:@"Frameworks"]; }
- (NSString *)docsPath {
    return NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
}

// ----- loading screen ------------------------------------------------------------------------

- (UIView *)buildSplash:(CGRect)bounds {
    RegisterToonFont([self dataPath]);          // so the title below already has the lettering font on the very first start
    UIView *v = [[UIView alloc] initWithFrame:bounds];
    CAGradientLayer *g = [CAGradientLayer layer];
    g.frame = bounds;
    g.colors = @[(id)[UIColor colorWithRed:0.42 green:0.74 blue:1.0 alpha:1].CGColor,
                 (id)[UIColor colorWithRed:0.10 green:0.30 blue:0.80 alpha:1].CGColor];
    [v.layer addSublayer:g];
    v.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;

    NSMutableArray *fb = [NSMutableArray array];
    // soft "splash" circles
    for (int i = 0; i < 7; i++) {
        CGFloat d = 80 + (i * 53) % 150;
        UIView *c = [[UIView alloc] initWithFrame:CGRectMake((i * 211) % (int)bounds.size.width, (i * 97) % (int)bounds.size.height, d, d)];
        c.backgroundColor = [UIColor colorWithWhite:1 alpha:0.07];
        c.layer.cornerRadius = d / 2;
        [v addSubview:c];
        [fb addObject:c];
    }

    UIFont *title = ToonFont(84);
    UILabel *t = [[UILabel alloc] init];
    t.attributedText = Outlined(@"TOONTOWN: ANYWHERE", ToonFont(84), [UIColor colorWithRed:1.0 green:0.851 blue:0.149 alpha:1],
                                [UIColor colorWithRed:0.11 green:0.247 blue:0.612 alpha:1], 6);
    t.adjustsFontSizeToFitWidth = YES;
    t.minimumScaleFactor = 0.5;
    t.font = title;
    t.textColor = [UIColor colorWithRed:1.0 green:0.85 blue:0.15 alpha:1];
    t.layer.shadowColor = [UIColor blackColor].CGColor;
    t.layer.shadowOffset = CGSizeMake(0, 5);
    t.layer.shadowOpacity = 0.5;
    t.layer.shadowRadius = 0;
    t.textAlignment = NSTextAlignmentCenter;
    t.tag = 7001;
    t.frame = CGRectMake(0, bounds.size.height * 0.16, bounds.size.width, 100);
    t.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleBottomMargin;
    [v addSubview:t];
    [fb addObject:t];

    UILabel *sub = [[UILabel alloc] init];
    sub.text = @"Unofficial mobile client";
    sub.font = ToonFont(28);
    sub.textColor = [UIColor colorWithWhite:1 alpha:0.9];
    sub.textAlignment = NSTextAlignmentCenter;
    sub.frame = CGRectMake(0, bounds.size.height * 0.16 + 92, bounds.size.width, 36);
    sub.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleBottomMargin;
    [v addSubview:sub];
    [fb addObject:sub];
    self.fallbackViews = fb;
    self.gradient = g;

    CGFloat bw = MIN(bounds.size.width * 0.6, 640);
    self.bar = [[UIProgressView alloc] initWithProgressViewStyle:UIProgressViewStyleDefault];
    self.bar.frame = CGRectMake((bounds.size.width - bw) / 2, bounds.size.height * 0.68, bw, 18);
    self.bar.transform = CGAffineTransformMakeScale(1, 3.2);
    self.bar.progressTintColor = [UIColor colorWithRed:1.0 green:0.85 blue:0.15 alpha:1];
    self.bar.trackTintColor = [UIColor colorWithWhite:0 alpha:0.25];
    self.bar.layer.cornerRadius = 6;
    self.bar.clipsToBounds = YES;
    self.bar.autoresizingMask = UIViewAutoresizingFlexibleLeftMargin | UIViewAutoresizingFlexibleRightMargin | UIViewAutoresizingFlexibleTopMargin;
    [v addSubview:self.bar];

    self.statusLabel = [[UILabel alloc] initWithFrame:CGRectMake(0, bounds.size.height * 0.68 + 28, bounds.size.width, 36)];
    self.statusLabel.textAlignment = NSTextAlignmentCenter;
    self.statusLabel.font = ToonFont(26);
    self.statusLabel.textColor = [UIColor whiteColor];
    self.statusLabel.attributedText = Outlined(@"Getting ready...", ToonFont(26), [UIColor whiteColor], [UIColor colorWithRed:0.11 green:0.247 blue:0.612 alpha:1], 5);
    self.statusLabel.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleTopMargin;
    [v addSubview:self.statusLabel];

    self.detailLabel = [[UILabel alloc] initWithFrame:CGRectMake(0, bounds.size.height * 0.68 + 66, bounds.size.width, 28)];
    self.detailLabel.textAlignment = NSTextAlignmentCenter;
    self.detailLabel.font = [UIFont systemFontOfSize:16 weight:UIFontWeightMedium];
    self.detailLabel.textColor = [UIColor colorWithWhite:1 alpha:0.75];
    self.detailLabel.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleTopMargin;
    [v addSubview:self.detailLabel];

    self.spinner = [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleLarge];
    self.spinner.color = [UIColor whiteColor];
    self.spinner.center = CGPointMake(bounds.size.width / 2, bounds.size.height * 0.5);
    self.spinner.hidesWhenStopped = YES;
    self.spinner.autoresizingMask = UIViewAutoresizingFlexibleLeftMargin | UIViewAutoresizingFlexibleRightMargin | UIViewAutoresizingFlexibleTopMargin | UIViewAutoresizingFlexibleBottomMargin;
    [v addSubview:self.spinner];

    self.errorView = [[UITextView alloc] initWithFrame:CGRectMake(40, bounds.size.height * 0.30, bounds.size.width - 80, bounds.size.height * 0.36)];
    self.errorView.backgroundColor = [UIColor colorWithWhite:0 alpha:0.45];
    self.errorView.textColor = [UIColor colorWithRed:1 green:0.85 blue:0.85 alpha:1];
    self.errorView.font = [UIFont fontWithName:@"Menlo" size:12];
    self.errorView.editable = NO;
    self.errorView.layer.cornerRadius = 12;
    self.errorView.hidden = YES;
    [v addSubview:self.errorView];
    return v;
}

// ----- start-screen art ----------------------------------------------------------------------

- (void)applyArt {
    RegisterToonFont([self dataPath]);
    if (self.bgView) return;
    NSString *bgPath = UIFilePath([self dataPath], @"background.jpg"), *logoPath = UIFilePath([self dataPath], @"logo.png");
    UIImage *bg = bgPath ? [UIImage imageWithContentsOfFile:bgPath] : nil;
    UIImage *logo = logoPath ? [UIImage imageWithContentsOfFile:logoPath] : nil;
    if (!bg) return;                    // (no logo picture is fine: the outlined lettering stays as the title)
    UIView *root = self.window.rootViewController.view;
    CGRect b = root.bounds;
    self.bgView = [[UIImageView alloc] initWithImage:bg];
    self.bgView.frame = b;
    self.bgView.contentMode = UIViewContentModeScaleAspectFill;
    self.bgView.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [root insertSubview:self.bgView atIndex:0];
    if (logo) {
        CGFloat lh = MIN(b.size.height * 0.40, 200 * UIScale()), lw = lh * logo.size.width / logo.size.height;
        self.logoView = [[UIImageView alloc] initWithImage:logo];
        self.logoView.frame = CGRectMake((b.size.width - lw) / 2, MAX(b.size.height * 0.04, 10), lw, lh);
        self.logoView.userInteractionEnabled = NO;
        self.logoView.autoresizingMask = UIViewAutoresizingFlexibleLeftMargin | UIViewAutoresizingFlexibleRightMargin | UIViewAutoresizingFlexibleBottomMargin;
    }
    self.bgView.userInteractionEnabled = NO;
    if (self.logoView) [root insertSubview:self.logoView aboveSubview:self.bgView];
    for (UIView *f in self.fallbackViews) f.hidden = YES;                      // the splash circles and the subtitle give way to the sky
    for (UIView *f in self.fallbackViews) if (f.tag == 7001 && !self.logoView) f.hidden = NO;      // the lettering stays when there is no logo picture
    self.gradient.hidden = YES;
}

// ----- sign in -------------------------------------------------------------------------------

static NSString *const kService = @"com.puffsco.toontownanywhere";

static NSString *ServerId(NSString *res, NSString *game) {
    NSData *d = [[NSString stringWithFormat:@"%@|%@", res.lowercaseString, game.lowercaseString] dataUsingEncoding:NSUTF8StringEncoding];
    unsigned char h[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256(d.bytes, (CC_LONG)d.length, h);
    NSMutableString *s = [NSMutableString string];
    for (int i = 0; i < 6; i++) [s appendFormat:@"%02x", h[i]];
    return s;
}

// Which server the player picked. The default server keeps the old storage places (so existing installs
// carry on untouched); any other server gets its own folder, saved name and keychain entry.
- (BOOL)loadServerChoice {
    NSUserDefaults *u = [NSUserDefaults standardUserDefaults];
    NSString *mode = [u stringForKey:@"tta_srv_mode"];
    if (!mode) {
        // installs from before the picker already hold the default server's files: keep using it
        if ([[NSFileManager defaultManager] fileExistsAtPath:[[self docsPath] stringByAppendingPathComponent:@"resources"]]) mode = @"default";
        else return NO;
    }
    NSString *res = [u stringForKey:@"tta_srv_res"], *game = [u stringForKey:@"tta_srv_game"];
    if ([mode isEqualToString:@"custom"] && res.length && game.length) {
        self.serverRes = res;
        self.serverGame = game;
        self.serverIsDefault = NO;
    } else {
        self.serverRes = RESOURCE_SERVER;
        self.serverGame = GAME_SERVER;
        self.serverIsDefault = YES;
    }
    return YES;
}

- (NSString *)dataPath {
    if (self.serverIsDefault || !self.serverRes) return [self docsPath];
    NSString *p = [[[self docsPath] stringByAppendingPathComponent:@"servers"] stringByAppendingPathComponent:ServerId(self.serverRes, self.serverGame)];
    [[NSFileManager defaultManager] createDirectoryAtPath:p withIntermediateDirectories:YES attributes:nil error:nil];
    return p;
}

- (NSString *)keychainService {
    return self.serverIsDefault ? kService : [kService stringByAppendingFormat:@".%@", ServerId(self.serverRes, self.serverGame)];
}

- (NSString *)userKey {
    return self.serverIsDefault ? @"tta_user" : [@"tta_user_" stringByAppendingString:ServerId(self.serverRes, self.serverGame)];
}

- (NSString *)keychainPassword {
    NSDictionary *q = @{(__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword, (__bridge id)kSecAttrService: [self keychainService],
                        (__bridge id)kSecReturnData: @YES, (__bridge id)kSecMatchLimit: (__bridge id)kSecMatchLimitOne};
    CFTypeRef out = NULL;
    if (SecItemCopyMatching((__bridge CFDictionaryRef)q, &out) != errSecSuccess || !out) return nil;
    return [[NSString alloc] initWithData:(__bridge_transfer NSData *)out encoding:NSUTF8StringEncoding];
}

- (void)saveKeychainPassword:(NSString *)pw {
    NSDictionary *q = @{(__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword, (__bridge id)kSecAttrService: [self keychainService]};
    SecItemDelete((__bridge CFDictionaryRef)q);
    NSMutableDictionary *a = [q mutableCopy];
    a[(__bridge id)kSecValueData] = [pw dataUsingEncoding:NSUTF8StringEncoding];
    a[(__bridge id)kSecAttrAccessible] = (__bridge id)kSecAttrAccessibleAfterFirstUnlock;
    SecItemAdd((__bridge CFDictionaryRef)a, NULL);
}

- (UITextField *)fieldWithPlaceholder:(NSString *)ph y:(CGFloat)y secure:(BOOL)secure width:(CGFloat)w {
    CGRect b = self.window.rootViewController.view.bounds;
    UITextField *f = [[UITextField alloc] initWithFrame:CGRectMake((b.size.width - w) / 2, y, w, 44 * UIScale())];
    f.backgroundColor = [UIColor colorWithWhite:1 alpha:0.92];
    f.layer.cornerRadius = 14;
    f.layer.borderWidth = 3;
    f.layer.borderColor = [UIColor colorWithRed:0.12 green:0.30 blue:0.65 alpha:1].CGColor;
    f.font = ToonFont(24 * UIScale());
    f.textColor = [UIColor colorWithRed:0.1 green:0.2 blue:0.45 alpha:1];
    f.attributedPlaceholder = [[NSAttributedString alloc] initWithString:ph attributes:@{NSForegroundColorAttributeName: [UIColor colorWithWhite:0.5 alpha:1]}];
    f.textAlignment = NSTextAlignmentCenter;
    f.secureTextEntry = secure;
    f.autocapitalizationType = UITextAutocapitalizationTypeNone;
    f.autocorrectionType = UITextAutocorrectionTypeNo;
    f.spellCheckingType = UITextSpellCheckingTypeNo;
    f.returnKeyType = secure ? UIReturnKeyGo : UIReturnKeyNext;
    f.delegate = (id<UITextFieldDelegate>)self;
    return f;
}

- (void)showLogin {
    RegisterToonFont([self dataPath]);
    [self.spinner stopAnimating];
    self.bar.hidden = YES;
    self.statusLabel.hidden = YES;
    self.detailLabel.hidden = YES;
    CGRect b = self.window.rootViewController.view.bounds;
    CGFloat sc = UIScale();
    CGFloat w = MIN(b.size.width * 0.5, 380 * sc);
    CGFloat y0 = b.size.height * (self.logoView ? 0.47 : 0.36);
    self.loginView = [[UIView alloc] initWithFrame:b];
    self.loginView.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    self.userField = [self fieldWithPlaceholder:@"Toon name" y:y0 secure:NO width:w];
    self.passField = [self fieldWithPlaceholder:@"Password" y:y0 + 52 * sc secure:YES width:w];
    self.userField.text = [[NSUserDefaults standardUserDefaults] stringForKey:[self userKey]];
    self.passField.text = [self keychainPassword];
    self.playButton = [UIButton buttonWithType:UIButtonTypeCustom];
    self.playButton.frame = CGRectMake((b.size.width - 220 * sc) / 2, y0 + 106 * sc, 220 * sc, 48 * sc);
    self.playButton.backgroundColor = [UIColor colorWithRed:1.0 green:0.85 blue:0.15 alpha:1];
    self.playButton.layer.cornerRadius = 18;
    self.playButton.layer.borderWidth = 4;
    self.playButton.layer.borderColor = [UIColor colorWithRed:0.55 green:0.32 blue:0.05 alpha:1].CGColor;
    [self.playButton setTitle:@"PLAY!" forState:UIControlStateNormal];
    [self.playButton setTitleColor:[UIColor colorWithRed:0.45 green:0.22 blue:0.02 alpha:1] forState:UIControlStateNormal];
    self.playButton.titleLabel.font = ToonFont(30 * sc);
    [self.playButton addTarget:self action:@selector(signIn) forControlEvents:UIControlEventTouchUpInside];
    UIButton *forgot = [UIButton buttonWithType:UIButtonTypeCustom];
    forgot.frame = CGRectMake(CGRectGetMaxX(self.playButton.frame) + 10 * sc, y0 + 106 * sc, 150 * sc, 48 * sc);
    [forgot setTitle:@"Forgot password?" forState:UIControlStateNormal];
    [forgot setTitleColor:[UIColor colorWithRed:0.08 green:0.2 blue:0.55 alpha:1] forState:UIControlStateNormal];
    forgot.titleLabel.font = [UIFont systemFontOfSize:14 * sc weight:UIFontWeightBold];
    forgot.titleLabel.adjustsFontSizeToFitWidth = YES;
    forgot.titleLabel.minimumScaleFactor = 0.7;
    [forgot addTarget:self action:@selector(forgotPassword) forControlEvents:UIControlEventTouchUpInside];
    self.loginError = [[UILabel alloc] initWithFrame:CGRectMake(40, y0 + 160 * sc, b.size.width - 80, 26 * sc)];
    self.loginError.textAlignment = NSTextAlignmentCenter;
    self.loginError.font = ToonFont(17 * sc);
    self.loginError.textColor = [UIColor colorWithRed:0.1 green:0.25 blue:0.55 alpha:1];
    self.loginError.text = @"New here? Pick a name and password and tap PLAY!";
    // credit
    UILabel *credit = [[UILabel alloc] initWithFrame:CGRectMake(20, b.size.height - 22 * sc - MAX(self.window.safeAreaInsets.bottom, 4), b.size.width - 40, 18 * sc)];
    credit.text = @"Official client for Toontown: Anywhere";
    credit.textAlignment = NSTextAlignmentCenter;
    credit.font = [UIFont systemFontOfSize:11 * sc weight:UIFontWeightSemibold];
    credit.textColor = [UIColor colorWithRed:0.08 green:0.2 blue:0.45 alpha:0.9];
    credit.adjustsFontSizeToFitWidth = YES;
    credit.minimumScaleFactor = 0.6;
    credit.userInteractionEnabled = NO;
    [self.loginView addSubview:credit];
    UIButton *chg = [self pillButton:@"Change server" frame:CGRectMake(b.size.width - 126 * sc - 14 - self.window.safeAreaInsets.right, MAX(self.window.safeAreaInsets.top, 6) + 8, 126 * sc, 30 * sc)
                                fill:[UIColor colorWithWhite:1 alpha:0.85] text:[UIColor colorWithRed:0.1 green:0.2 blue:0.5 alpha:1] size:13 * sc];
    chg.layer.borderWidth = 2;
    chg.layer.cornerRadius = 12;
    [chg addTarget:self action:@selector(changeServer) forControlEvents:UIControlEventTouchUpInside];
    [self.loginView addSubview:chg];
    UIButton *setBtn = [self pillButton:@"Settings" frame:CGRectMake(chg.frame.origin.x, CGRectGetMaxY(chg.frame) + 8, 126 * sc, 30 * sc)
                                   fill:[UIColor colorWithWhite:1 alpha:0.85] text:[UIColor colorWithRed:0.1 green:0.2 blue:0.5 alpha:1] size:13 * sc];
    setBtn.layer.borderWidth = 2;
    setBtn.layer.cornerRadius = 12;
    [setBtn addTarget:self action:@selector(openSettings) forControlEvents:UIControlEventTouchUpInside];
    [self.loginView addSubview:setBtn];
    CGFloat lby = b.size.height - MAX(self.window.safeAreaInsets.bottom, 4) - 22 * sc - 8 - 30 * sc;
    CGFloat lbx = 14 + self.window.safeAreaInsets.left;
    UIButton *dis = [self linkButton:@"Discord" icon:kDiscordIcon fill:[UIColor colorWithRed:0.345 green:0.396 blue:0.949 alpha:1]
                               frame:CGRectMake(lbx, lby - 38 * sc, 112 * sc, 30 * sc) tag:0 size:13 * sc];
    UIButton *red = [self linkButton:@"Reddit" icon:kRedditIcon fill:[UIColor colorWithRed:1.0 green:0.27 blue:0.0 alpha:1]
                               frame:CGRectMake(lbx, lby, 112 * sc, 30 * sc) tag:1 size:13 * sc];
    [self.loginView addSubview:dis];
    [self.loginView addSubview:red];
    self.loginView.userInteractionEnabled = YES;
    self.userField.userInteractionEnabled = YES;
    self.passField.userInteractionEnabled = YES;
    for (UIView *x in @[self.userField, self.passField, self.playButton, forgot, self.loginError]) [self.loginView addSubview:x];
    for (UITextField *tf in @[self.userField, self.passField]) {
        UITapGestureRecognizer *tap = [[UITapGestureRecognizer alloc] initWithTarget:tf action:@selector(becomeFirstResponder)];
        tap.cancelsTouchesInView = NO;
        [tf addGestureRecognizer:tap];
    }
    // its own window (like the game controls): touches reach it reliably
    self.loginWindow = NewWindow([UIWindow class], SceneBounds());
    self.loginWindow.windowLevel = UIWindowLevelAlert;
    self.loginWindow.backgroundColor = [UIColor clearColor];
    TTAViewController *lvc = [TTAViewController new];
    lvc.view.backgroundColor = [UIColor clearColor];
    self.loginWindow.rootViewController = lvc;
    self.loginView.frame = lvc.view.bounds;
    [lvc.view addSubview:self.loginView];
    [self.loginWindow makeKeyAndVisible];
    self.lastLoginSize = lvc.view.bounds.size;
    __weak AppDelegate *weakSelf = self;
    lvc.onLayout = ^(CGSize size) {         // a rotation or a foldable opening or closing: lay the sign-in screen out again for the new shape
        AppDelegate *me = weakSelf;
        if (!me || me.userField.isFirstResponder || me.passField.isFirstResponder) return;
        if (fabs(size.width - me.lastLoginSize.width) < 1 && fabs(size.height - me.lastLoginSize.height) < 1) return;
        me.lastLoginSize = size;
        dispatch_async(dispatch_get_main_queue(), ^{ [me rebuildLogin]; });
    };
    [[NSNotificationCenter defaultCenter] removeObserver:self name:UIKeyboardWillShowNotification object:nil];
    [[NSNotificationCenter defaultCenter] removeObserver:self name:UIKeyboardWillHideNotification object:nil];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(keyboardChange:) name:UIKeyboardWillShowNotification object:nil];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(keyboardChange:) name:UIKeyboardWillHideNotification object:nil];
}

// Builds the sign-in screen again for a new screen shape, keeping what was typed.
- (void)rebuildLogin {
    if (!self.loginWindow || self.loginWindow.hidden) return;
    NSString *u = self.userField.text, *p = self.passField.text, *err = self.loginError.text;
    self.loginWindow.hidden = YES;
    self.loginWindow = nil;
    self.loginView = nil;
    [self showLogin];
    self.userField.text = u;
    self.passField.text = p;
    self.loginError.text = err;
}

- (void)keyboardChange:(NSNotification *)n {
    BOOL show = [n.name isEqualToString:UIKeyboardWillShowNotification];
    [UIView animateWithDuration:0.25 animations:^{
        self.loginView.transform = show ? CGAffineTransformMakeTranslation(0, -(self.userField.frame.origin.y - 12)) : CGAffineTransformIdentity;
        self.logoView.alpha = show ? 0.0 : 1.0;
    }];
}

- (BOOL)textFieldShouldReturn:(UITextField *)f {
    if (f == self.kbField) {
        pyRun("import ios_game\nios_game.ui_text_submit()\n");
        [f resignFirstResponder];
        self.kbActive = NO;
        return NO;
    }
    if (f == self.recNick) { [self.recToon becomeFirstResponder]; return NO; }
    if (f == self.recToon) { if (self.recPw) [self.recPw becomeFirstResponder]; else [self submitRecoveryPrimary]; return NO; }
    if (f == self.recPw) { [self submitRecoveryPrimary]; return NO; }
    if (f == self.resField) { [self.gameField becomeFirstResponder]; return NO; }
    if (f == self.gameField) { [self connectCustom]; return NO; }
    if (f == self.userField) [self.passField becomeFirstResponder];
    else [self signIn];
    return NO;
}

- (void)loginMessage:(NSString *)m bad:(BOOL)bad {
    self.loginError.textColor = bad ? [UIColor colorWithRed:0.85 green:0.1 blue:0.1 alpha:1] : [UIColor colorWithRed:0.1 green:0.25 blue:0.55 alpha:1];
    self.loginError.text = m;
}

- (void)signIn {
    [self.loginWindow endEditing:YES];
    NSString *user = [[self.userField.text stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceCharacterSet]] lowercaseString];
    NSString *pw = self.passField.text ?: @"";
    if (user.length == 0 || pw.length == 0) {
        [self loginMessage:@"Enter your toon name and password." bad:YES];
        return;
    }
    if ([user containsString:@":"] || [user containsString:@"'"] || [pw containsString:@"'"] || [pw containsString:@"\\"]) {
        [self loginMessage:@"Please don't use quotes, colons or backslashes." bad:YES];
        return;
    }
    self.playButton.enabled = NO;
    [self loginMessage:@"Signing in..." bad:NO];
    NSString *cookie = [NSString stringWithFormat:@"%@:%@", user, pw];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSString *code = [NSString stringWithFormat:@"import ios_game\n_r = ios_game.check_login('%@', '%@')\n", self.serverRes, cookie];
        NSString *r = pyString(code.UTF8String, "_r");
        dispatch_async(dispatch_get_main_queue(), ^{
            if ([r isEqualToString:@"ok"] || [r isEqualToString:@"setup"]) {
                void (^proceed)(void) = ^{
                [[NSUserDefaults standardUserDefaults] setObject:user forKey:[self userKey]];
                [self saveKeychainPassword:pw];
                [self.loginView removeFromSuperview];
                self.loginWindow.hidden = YES;
                self.loginWindow = nil;
                [[NSNotificationCenter defaultCenter] removeObserver:self name:UIKeyboardWillShowNotification object:nil];
                [[NSNotificationCenter defaultCenter] removeObserver:self name:UIKeyboardWillHideNotification object:nil];
                self.statusLabel.hidden = NO;
                self.statusLabel.text = @"Starting Toontown...";
                [self.spinner startAnimating];
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.3 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                    [self launchGameWithCookie:cookie];
                });
                };
                if ([r isEqualToString:@"setup"]) [self askRecoverySetupFor:cookie done:proceed];
                else proceed();
            } else {
                self.playButton.enabled = YES;
                [self loginMessage:(r ?: @"Sign-in failed.") bad:YES];
            }
        });
    });
}

// ----- password recovery ---------------------------------------------------------------------

static NSString *HexOf(NSString *s) {
    NSData *d = [s dataUsingEncoding:NSUTF8StringEncoding];
    const unsigned char *b = d.bytes;
    NSMutableString *h = [NSMutableString string];
    for (NSUInteger i = 0; i < d.length; i++) [h appendFormat:@"%02x", b[i]];
    return h;
}

- (void)recoveryPost:(NSString *)path text:(NSString *)text done:(void (^)(NSString *))done {
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSString *code = [NSString stringWithFormat:@"import ios_game\n_r = ios_game.recovery_call_hex('%@', '%@', '%@')\n", self.serverRes, path, HexOf(text)];
        NSString *r = pyString(code.UTF8String, "_r");
        dispatch_async(dispatch_get_main_queue(), ^{ done(r ?: @"That didn't work."); });
    });
}

// On-screen card (same look as the server card) used by both recovery steps.
- (void)showRecoveryCard:(NSString *)title blurb:(NSString *)blurb withPassword:(BOOL)withPw primary:(NSString *)primary secondary:(NSString *)secondary {
    self.loginWindow.hidden = YES;
    CGRect b = self.window.rootViewController.view.bounds;
    CGFloat sc = UIScale();
    CGFloat cw = MIN(b.size.width - 40, 520 * sc);
    CGFloat pad = 20 * sc, w = cw - 2 * pad;
    CGFloat ch = (withPw ? 392 : 344) * sc;
    CGFloat top = MAX(16, (b.size.height - ch) / 2);
    self.recScroll = [[UIScrollView alloc] initWithFrame:b];
    self.recScroll.contentSize = CGSizeMake(b.size.width, MAX(b.size.height, ch + 32));
    self.recScroll.alwaysBounceVertical = YES;
    self.recScroll.keyboardDismissMode = UIScrollViewKeyboardDismissModeInteractive;
    UIView *card = [[UIView alloc] initWithFrame:CGRectMake((b.size.width - cw) / 2, top, cw, ch)];
    card.backgroundColor = [UIColor colorWithWhite:1 alpha:0.95];
    card.layer.cornerRadius = 22;
    card.layer.borderWidth = 4;
    card.layer.borderColor = [UIColor colorWithRed:0.12 green:0.30 blue:0.65 alpha:1].CGColor;
    [self.recScroll addSubview:card];
    [card addSubview:[self cardLabel:title frame:CGRectMake(pad, 12 * sc, w, 34 * sc) size:26 * sc bold:YES]];
    [card addSubview:[self cardLabel:blurb frame:CGRectMake(pad, 50 * sc, w, 44 * sc) size:14 * sc bold:NO]];

    self.recNick = [self fieldWithPlaceholder:@"Your nickname" y:0 secure:NO width:w];
    self.recToon = [self fieldWithPlaceholder:@"A toon name you made" y:0 secure:NO width:w];
    NSMutableArray *fields = [NSMutableArray arrayWithObjects:self.recNick, self.recToon, nil];
    self.recPw = nil;
    if (withPw) {
        self.recPw = [self fieldWithPlaceholder:@"New password" y:0 secure:YES width:w];
        [fields addObject:self.recPw];
    }
    CGFloat y = 100 * sc;
    for (UITextField *f in fields) {
        f.frame = CGRectMake(pad, y, w, 42 * sc);
        f.font = [UIFont systemFontOfSize:18 * sc weight:UIFontWeightSemibold];
        f.returnKeyType = (f == fields.lastObject) ? UIReturnKeyGo : UIReturnKeyNext;
        [card addSubview:f];
        y += 48 * sc;
    }
    self.recMsg = [self cardLabel:@"" frame:CGRectMake(pad, y + 2 * sc, w, 34 * sc) size:14 * sc bold:NO];
    [card addSubview:self.recMsg];
    y += 40 * sc;
    self.recPrimary = [self pillButton:primary frame:CGRectMake((cw - 220 * sc) / 2, y, 220 * sc, 44 * sc)
                                  fill:[UIColor colorWithRed:0.35 green:0.65 blue:1.0 alpha:1] text:[UIColor whiteColor] size:22 * sc];
    [self.recPrimary addTarget:self action:@selector(submitRecoveryPrimary) forControlEvents:UIControlEventTouchUpInside];
    [card addSubview:self.recPrimary];
    self.recSecondary = [self pillButton:secondary frame:CGRectMake((cw - 160 * sc) / 2, y + 52 * sc, 160 * sc, 32 * sc)
                                    fill:[UIColor colorWithWhite:0.92 alpha:1] text:[UIColor colorWithRed:0.1 green:0.2 blue:0.5 alpha:1] size:16 * sc];
    self.recSecondary.layer.borderWidth = 2;
    [self.recSecondary addTarget:self action:@selector(recoverySecondary) forControlEvents:UIControlEventTouchUpInside];
    [card addSubview:self.recSecondary];

    self.recWindow = NewWindow([UIWindow class], SceneBounds());
    self.recWindow.windowLevel = UIWindowLevelAlert;
    self.recWindow.backgroundColor = [UIColor clearColor];
    UIViewController *rvc = [UIViewController new];
    rvc.view.backgroundColor = [UIColor clearColor];
    self.recWindow.rootViewController = rvc;
    self.recScroll.frame = rvc.view.bounds;
    self.recScroll.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [rvc.view addSubview:self.recScroll];
    [self.recWindow makeKeyAndVisible];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(serverKeyboard:) name:UIKeyboardWillChangeFrameNotification object:nil];
}

- (void)closeRecoveryCard {
    [[NSNotificationCenter defaultCenter] removeObserver:self name:UIKeyboardWillChangeFrameNotification object:nil];
    [self.recWindow endEditing:YES];
    self.recWindow.hidden = YES;
    self.recWindow = nil;
    self.recScroll = nil;
    self.recNick = nil;
    self.recToon = nil;
    self.recPw = nil;
}

- (void)recoveryMessage:(NSString *)t bad:(BOOL)bad {
    self.recMsg.textColor = bad ? [UIColor colorWithRed:0.85 green:0.1 blue:0.1 alpha:1] : [UIColor colorWithRed:0.1 green:0.25 blue:0.55 alpha:1];
    self.recMsg.text = t;
}

// After sign-in on an account with no recovery answers yet.
- (void)askRecoverySetupFor:(NSString *)cookie done:(void (^)(void))done {
    self.recReset = NO;
    self.recCookie = cookie;
    self.recDone = done;
    [self showRecoveryCard:@"Forgot-password help"
                     blurb:@"Pick two answers only you will remember. If you ever forget your password, they let you set a new one."
              withPassword:NO primary:@"Save" secondary:@"Skip for now"];
}

// "Forgot password?" on the sign-in screen.
- (void)forgotPassword {
    [self.loginWindow endEditing:YES];
    NSString *user = [[self.userField.text stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceCharacterSet]] lowercaseString];
    if (user.length == 0) {
        [self loginMessage:@"Type your toon name above first, then tap Forgot password." bad:YES];
        return;
    }
    self.recReset = YES;
    self.recUser = user;
    self.recDone = nil;
    [self showRecoveryCard:@"Reset password"
                     blurb:[NSString stringWithFormat:@"Answer the two questions you saved for %@, then pick a new password.", user]
              withPassword:YES primary:@"Reset password" secondary:@"Cancel"];
}

- (void)recoverySecondary {
    void (^d)(void) = self.recDone;
    BOOL reset = self.recReset;
    [self closeRecoveryCard];
    if (reset) self.loginWindow.hidden = NO;
    else if (d) d();
}

- (void)submitRecoveryPrimary {
    [self.recWindow endEditing:YES];
    NSCharacterSet *ws = [NSCharacterSet whitespaceAndNewlineCharacterSet];
    NSString *nick = [(self.recNick.text ?: @"") stringByTrimmingCharactersInSet:ws];
    NSString *toon = [(self.recToon.text ?: @"") stringByTrimmingCharactersInSet:ws];
    NSString *pw = self.recPw.text ?: @"";
    if (nick.length == 0 || toon.length == 0 || (self.recReset && pw.length == 0)) {
        [self recoveryMessage:@"Fill in every box." bad:YES];
        return;
    }
    NSString *path, *text;
    if (self.recReset) {
        if ([pw containsString:@"'"] || [pw containsString:@"\\"] || [pw containsString:@":"]) {
            [self recoveryMessage:@"Please don't use quotes, colons or backslashes." bad:YES];
            return;
        }
        path = @"/recover";
        text = [NSString stringWithFormat:@"%@\n%@\n%@\n%@", self.recUser, nick, toon, pw];
    } else {
        path = @"/setrecovery";
        text = [NSString stringWithFormat:@"%@\n%@\n%@", self.recCookie, nick, toon];
    }
    self.recPrimary.enabled = NO;
    self.recSecondary.enabled = NO;
    [self recoveryMessage:(self.recReset ? @"Checking..." : @"Saving...") bad:NO];
    [self recoveryPost:path text:text done:^(NSString *r) {
        self.recPrimary.enabled = YES;
        self.recSecondary.enabled = YES;
        if (![r isEqualToString:@"ok"]) {
            [self recoveryMessage:r bad:YES];
            return;
        }
        void (^d)(void) = self.recDone;
        BOOL reset = self.recReset;
        [self closeRecoveryCard];
        if (reset) {
            self.passField.text = pw;
            self.loginWindow.hidden = NO;
            [self loginMessage:@"Password changed! Tap PLAY." bad:NO];
        } else if (d) {
            d();
        }
    }];
}

// ----- server choice -------------------------------------------------------------------------

- (UIButton *)linkButton:(NSString *)title icon:(NSString *)b64 fill:(UIColor *)fill frame:(CGRect)f tag:(NSInteger)tag size:(CGFloat)size {
    UIButton *b = [self pillButton:title frame:f fill:fill text:[UIColor whiteColor] size:size];
    b.layer.cornerRadius = 12;
    b.layer.borderWidth = 2;
    b.layer.borderColor = [UIColor colorWithWhite:1 alpha:0.9].CGColor;
    [b setImage:LinkIcon(b64, f.size.height * 0.62) forState:UIControlStateNormal];
    b.imageView.contentMode = UIViewContentModeScaleAspectFit;
    b.imageEdgeInsets = UIEdgeInsetsMake(0, -4, 0, 4);
    b.titleEdgeInsets = UIEdgeInsetsMake(0, 4, 0, -4);
    b.tag = tag;
    [b addTarget:self action:@selector(openCommunityLink:) forControlEvents:UIControlEventTouchUpInside];
    return b;
}

- (void)openCommunityLink:(UIButton *)b {
    NSURL *u = [NSURL URLWithString:(b.tag == 0 ? kDiscordURL : kRedditURL)];
    if (u) [[UIApplication sharedApplication] openURL:u options:@{} completionHandler:nil];
}

- (UIButton *)pillButton:(NSString *)title frame:(CGRect)f fill:(UIColor *)fill text:(UIColor *)tc size:(CGFloat)size {
    UIButton *b = [UIButton buttonWithType:UIButtonTypeCustom];
    b.frame = f;
    b.backgroundColor = fill;
    b.layer.cornerRadius = 16;
    b.layer.borderWidth = 3;
    b.layer.borderColor = [UIColor colorWithRed:0.12 green:0.30 blue:0.65 alpha:1].CGColor;
    [b setTitle:title forState:UIControlStateNormal];
    [b setTitleColor:tc forState:UIControlStateNormal];
    [b setTitleColor:[tc colorWithAlphaComponent:0.4] forState:UIControlStateDisabled];
    b.titleLabel.font = ToonFont(size);
    b.titleLabel.adjustsFontSizeToFitWidth = YES;
    b.titleLabel.minimumScaleFactor = 0.6;
    return b;
}

- (UILabel *)cardLabel:(NSString *)text frame:(CGRect)f size:(CGFloat)size bold:(BOOL)bold {
    UILabel *l = [[UILabel alloc] initWithFrame:f];
    l.text = text;
    l.textAlignment = NSTextAlignmentCenter;
    l.numberOfLines = 0;
    l.adjustsFontSizeToFitWidth = YES;
    l.minimumScaleFactor = 0.7;
    l.font = bold ? (ToonFont(size)) : [UIFont systemFontOfSize:size weight:UIFontWeightSemibold];
    l.textColor = [UIColor colorWithRed:0.1 green:0.2 blue:0.45 alpha:1];
    return l;
}

- (void)showServerChoiceCanGoBack:(BOOL)back {
    [self.spinner stopAnimating];
    self.bar.hidden = YES;
    self.statusLabel.hidden = YES;
    self.detailLabel.hidden = YES;
    self.errorView.hidden = YES;
    self.changeServerBtn.hidden = YES;
    self.loginWindow.hidden = YES;
    CGRect b = self.window.rootViewController.view.bounds;
    CGFloat sc = UIScale();
    CGFloat cw = MIN(b.size.width - 40, 520 * sc);
    CGFloat pad = 20 * sc;
    CGFloat ch = (back ? 430 : 392) * sc;
    CGFloat top = MAX(16, (b.size.height - ch) / 2);

    self.serverScroll = [[UIScrollView alloc] initWithFrame:b];
    self.serverScroll.contentSize = CGSizeMake(b.size.width, MAX(b.size.height, ch + 32));
    self.serverScroll.alwaysBounceVertical = YES;
    self.serverScroll.keyboardDismissMode = UIScrollViewKeyboardDismissModeInteractive;
    UIView *card = [[UIView alloc] initWithFrame:CGRectMake((b.size.width - cw) / 2, top, cw, ch)];
    card.backgroundColor = [UIColor colorWithWhite:1 alpha:0.95];
    card.layer.cornerRadius = 22;
    card.layer.borderWidth = 4;
    card.layer.borderColor = [UIColor colorWithRed:0.12 green:0.30 blue:0.65 alpha:1].CGColor;
    [self.serverScroll addSubview:card];

    CGFloat w = cw - 2 * pad;
    [card addSubview:[self cardLabel:@"Choose a server" frame:CGRectMake(pad, 12 * sc, w, 34 * sc) size:26 * sc bold:YES]];
    self.defaultBtn = [self pillButton:@"Connect to Toontown: Anywhere" frame:CGRectMake(pad, 52 * sc, w, 48 * sc)
                                  fill:[UIColor colorWithRed:1.0 green:0.85 blue:0.15 alpha:1] text:[UIColor colorWithRed:0.45 green:0.22 blue:0.02 alpha:1] size:21 * sc];
    self.defaultBtn.layer.borderColor = [UIColor colorWithRed:0.55 green:0.32 blue:0.05 alpha:1].CGColor;
    [self.defaultBtn addTarget:self action:@selector(useDefaultServer) forControlEvents:UIControlEventTouchUpInside];
    [card addSubview:self.defaultBtn];
    NSString *host = [[GAME_SERVER componentsSeparatedByString:@":"] firstObject];
    [card addSubview:[self cardLabel:host frame:CGRectMake(pad, 102 * sc, w, 16 * sc) size:12 * sc bold:NO]];
    [card addSubview:[self cardLabel:@"or connect to a different server" frame:CGRectMake(pad, 128 * sc, w, 22 * sc) size:16 * sc bold:YES]];

    self.resField = [self fieldWithPlaceholder:@"File server  (https://...)" y:0 secure:NO width:w];
    self.gameField = [self fieldWithPlaceholder:@"Game server  (host:port)" y:0 secure:NO width:w];
    CGFloat fy[2] = {154 * sc, 202 * sc};
    int i = 0;
    for (UITextField *f in @[self.resField, self.gameField]) {
        f.frame = CGRectMake(pad, fy[i++], w, 42 * sc);
        f.font = [UIFont systemFontOfSize:17 * sc weight:UIFontWeightSemibold];
        f.keyboardType = UIKeyboardTypeURL;
        [card addSubview:f];
    }
    self.gameField.returnKeyType = UIReturnKeyGo;
    if (!self.serverIsDefault) {
        self.resField.text = self.serverRes;
        self.gameField.text = self.serverGame;
    }
    UILabel *warn = [self cardLabel:@"Only connect to servers you trust. A server supplies the game's code, which runs inside this app."
                              frame:CGRectMake(pad, 250 * sc, w, 34 * sc) size:11 * sc bold:NO];
    warn.textColor = [UIColor colorWithRed:0.45 green:0.2 blue:0.1 alpha:1];
    [card addSubview:warn];
    self.connectBtn = [self pillButton:@"Connect" frame:CGRectMake((cw - 200 * sc) / 2, 290 * sc, 200 * sc, 44 * sc)
                                  fill:[UIColor colorWithRed:0.35 green:0.65 blue:1.0 alpha:1] text:[UIColor whiteColor] size:22 * sc];
    [self.connectBtn addTarget:self action:@selector(connectCustom) forControlEvents:UIControlEventTouchUpInside];
    [card addSubview:self.connectBtn];
    self.serverMsg = [self cardLabel:@"" frame:CGRectMake(pad, 338 * sc, w, 38 * sc) size:14 * sc bold:NO];
    [card addSubview:self.serverMsg];
    if (back) {
        UIButton *bk = [self pillButton:@"Back" frame:CGRectMake((cw - 120 * sc) / 2, 384 * sc, 120 * sc, 32 * sc)
                                   fill:[UIColor colorWithWhite:0.92 alpha:1] text:[UIColor colorWithRed:0.1 green:0.2 blue:0.5 alpha:1] size:16 * sc];
        bk.layer.borderWidth = 2;
        [bk addTarget:self action:@selector(backFromServerChoice) forControlEvents:UIControlEventTouchUpInside];
        [card addSubview:bk];
    }

    self.serverWindow = NewWindow([UIWindow class], SceneBounds());
    self.serverWindow.windowLevel = UIWindowLevelAlert;
    self.serverWindow.backgroundColor = [UIColor clearColor];
    UIViewController *svc = [UIViewController new];
    svc.view.backgroundColor = [UIColor clearColor];
    self.serverWindow.rootViewController = svc;
    self.serverScroll.frame = svc.view.bounds;
    self.serverScroll.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [svc.view addSubview:self.serverScroll];
    [self.serverWindow makeKeyAndVisible];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(serverKeyboard:) name:UIKeyboardWillChangeFrameNotification object:nil];
}

- (void)serverKeyboard:(NSNotification *)n {
    UIScrollView *sv = self.serverScroll ?: self.recScroll;
    if (!sv) return;
    CGRect kb = [n.userInfo[UIKeyboardFrameEndUserInfoKey] CGRectValue];
    CGRect inView = [sv convertRect:kb fromView:nil];
    CGFloat h = MAX(0, CGRectGetMaxY(sv.bounds) - inView.origin.y);
    sv.contentInset = UIEdgeInsetsMake(0, 0, h, 0);
    sv.scrollIndicatorInsets = sv.contentInset;
    UITextField *ff = nil;
    for (UITextField *t in @[(id)self.resField ?: [NSNull null], (id)self.gameField ?: [NSNull null], (id)self.recNick ?: [NSNull null], (id)self.recToon ?: [NSNull null], (id)self.recPw ?: [NSNull null]]) {
        if ([t isKindOfClass:[UITextField class]] && t.isFirstResponder) ff = t;
    }
    if (ff && h > 0) [sv scrollRectToVisible:[sv convertRect:CGRectInset(ff.bounds, 0, -16) fromView:ff] animated:YES];
}

- (void)closeServerWindow {
    [[NSNotificationCenter defaultCenter] removeObserver:self name:UIKeyboardWillChangeFrameNotification object:nil];
    [self.serverWindow endEditing:YES];
    self.serverWindow.hidden = YES;
    self.serverWindow = nil;
    self.serverScroll = nil;
    self.resField = nil;
    self.gameField = nil;
}

- (void)changeServer { [self showServerChoiceCanGoBack:YES]; }
- (void)changeServerFromError { [self showServerChoiceCanGoBack:NO]; }

- (void)backFromServerChoice {
    [self closeServerWindow];
    self.loginWindow.hidden = NO;
}

- (void)useDefaultServer { [self chooseServerRes:RESOURCE_SERVER game:GAME_SERVER isDefault:YES]; }

- (void)serverMessage:(NSString *)t bad:(BOOL)bad {
    self.serverMsg.textColor = bad ? [UIColor colorWithRed:0.85 green:0.1 blue:0.1 alpha:1] : [UIColor colorWithRed:0.1 green:0.25 blue:0.55 alpha:1];
    self.serverMsg.text = t;
}

- (void)connectCustom {
    [self.serverWindow endEditing:YES];
    NSCharacterSet *ws = [NSCharacterSet whitespaceAndNewlineCharacterSet];
    NSString *res = [(self.resField.text ?: @"") stringByTrimmingCharactersInSet:ws];
    NSString *game = [(self.gameField.text ?: @"") stringByTrimmingCharactersInSet:ws];
    if (res.length == 0 || game.length == 0) {
        [self serverMessage:@"Fill in both boxes, or tap the button above." bad:YES];
        return;
    }
    NSMutableCharacterSet *ok = [[NSCharacterSet alphanumericCharacterSet] mutableCopy];
    [ok addCharactersInString:@".-:/_[]%"];
    if ([res rangeOfCharacterFromSet:ok.invertedSet].location != NSNotFound || [game rangeOfCharacterFromSet:ok.invertedSet].location != NSNotFound) {
        [self serverMessage:@"Those addresses have a character that isn't allowed." bad:YES];
        return;
    }
    self.connectBtn.enabled = NO;
    self.defaultBtn.enabled = NO;
    [self serverMessage:@"Checking the server..." bad:NO];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSString *code = [NSString stringWithFormat:@"import ios_game\n_r = ios_game.test_server_hex('%@', '%@')\n", HexOf(res), HexOf(game)];
        NSString *r = pyString(code.UTF8String, "_r");
        dispatch_async(dispatch_get_main_queue(), ^{
            self.connectBtn.enabled = YES;
            self.defaultBtn.enabled = YES;
            NSArray *p = [r componentsSeparatedByString:@"|"];
            if ([r hasPrefix:@"ok|"] && p.count == 3) {
                [self chooseServerRes:p[1] game:p[2] isDefault:NO];
            } else {
                [self serverMessage:(r.length ? r : @"Couldn't check that server.") bad:YES];
            }
        });
    });
}

// Remember the choice, then (re)start from the download step with that server.
- (void)chooseServerRes:(NSString *)res game:(NSString *)game isDefault:(BOOL)isDef {
    BOOL same = self.serverRes && [self.serverRes isEqualToString:res] && [self.serverGame isEqualToString:game] && self.loginWindow;
    NSUserDefaults *u = [NSUserDefaults standardUserDefaults];
    [u setObject:isDef ? @"default" : @"custom" forKey:@"tta_srv_mode"];
    if (!isDef) {
        [u setObject:res forKey:@"tta_srv_res"];
        [u setObject:game forKey:@"tta_srv_game"];
    }
    [self closeServerWindow];
    if (same) {
        self.loginWindow.hidden = NO;   // same server as before: nothing to redo
        return;
    }
    if (self.loginWindow) {
        [self.loginView removeFromSuperview];
        self.loginWindow.hidden = YES;
        self.loginWindow = nil;
        [[NSNotificationCenter defaultCenter] removeObserver:self name:UIKeyboardWillShowNotification object:nil];
        [[NSNotificationCenter defaultCenter] removeObserver:self name:UIKeyboardWillHideNotification object:nil];
    }
    [self loadServerChoice];
    // the old server's start-screen art goes; this server's cached art (if any) comes in
    [self.bgView removeFromSuperview];
    [self.logoView removeFromSuperview];
    self.bgView = nil;
    self.logoView = nil;
    for (UIView *f in self.fallbackViews) f.hidden = NO;
    self.gradient.hidden = NO;
    [self applyArt];
    [self beginDownload];
}

- (void)beginDownload {
    [self.poll invalidate];
    self.changeServerBtn.hidden = YES;
    self.errorView.hidden = YES;
    self.bar.hidden = NO;
    self.statusLabel.hidden = NO;
    self.detailLabel.hidden = NO;
    self.statusLabel.text = @"Getting ready...";
    self.detailLabel.text = @"";
    [self.bar setProgress:0];
    NSString *code = [NSString stringWithFormat:@"import ios_game\nios_game.start_download('%@', '%@')\n", [self dataPath], self.serverRes];
    pyRun(code.UTF8String);
    self.poll = [NSTimer scheduledTimerWithTimeInterval:0.25 target:self selector:@selector(pollDownload:) userInfo:nil repeats:YES];
}

- (void)setStatus:(NSString *)s detail:(NSString *)d progress:(float)p {
    self.statusLabel.text = s;
    self.detailLabel.text = d;
    if (p >= 0) [self.bar setProgress:p animated:NO];
}

- (void)showError:(NSString *)msg {
    [self.spinner stopAnimating];
    self.statusLabel.text = @"Something went wrong";
    self.errorView.text = msg;
    self.errorView.hidden = NO;
    if (!self.changeServerBtn) {
        CGRect b = self.window.rootViewController.view.bounds;
        self.changeServerBtn = [self pillButton:@"Change server" frame:CGRectMake((b.size.width - 170) / 2, b.size.height - 64, 170, 40)
                                           fill:[UIColor colorWithWhite:1 alpha:0.9] text:[UIColor colorWithRed:0.1 green:0.2 blue:0.5 alpha:1] size:16];
        self.changeServerBtn.autoresizingMask = UIViewAutoresizingFlexibleLeftMargin | UIViewAutoresizingFlexibleRightMargin | UIViewAutoresizingFlexibleTopMargin;
        [self.changeServerBtn addTarget:self action:@selector(changeServerFromError) forControlEvents:UIControlEventTouchUpInside];
        [self.window.rootViewController.view addSubview:self.changeServerBtn];
    }
    self.changeServerBtn.hidden = NO;
}

// ----- python / game ------------------------------------------------------------------------

- (NSString *)startPython {
    NSString *res = [self resPath];
    NSString *home = [res stringByAppendingPathComponent:@"python"];
    NSString *lib = [home stringByAppendingPathComponent:@"lib/python3.10"];
    NSString *pypath = [NSString stringWithFormat:@"%@:%@/lib-dynload:%@/app", lib, lib, res];
    setenv("PYTHONHOME", home.UTF8String, 1);
    setenv("PYTHONPATH", pypath.UTF8String, 1);
    // keep compiled .pyc files across launches so the 460k lines of game code are only compiled once
    setenv("PYTHONPYCACHEPREFIX", [[self docsPath] stringByAppendingPathComponent:@"pycache"].UTF8String, 1);
    setenv("PYTHONIOENCODING", "utf-8", 1);
    Py_Initialize();
    if (!Py_IsInitialized()) {
        return @"Py_Initialize failed";
    }
    PyEval_SaveThread();
    NSString *fw = [self fwPath];
    NSString *code = [NSString stringWithFormat:
        @"import sys\n"
         "try:\n"
         "    import ios_bootstrap\n"
         "    ios_bootstrap.install('%@')\n"
         "    import m2_test\n"
         "    _r = m2_test.run('%@')\n"
         "except BaseException:\n"
         "    import traceback\n"
         "    _r = 'm2_test failed\\n' + traceback.format_exc()\n"
         "_result = _r\n", fw, fw];
    return pyString(code.UTF8String, "_result");
}

- (void)pollDownload:(NSTimer *)timer {
    NSString *s = pyString("import ios_game\n_s = ios_game.ui_status()\n", "_s");
    NSArray *p = [s componentsSeparatedByString:@"|"];
    [self applyArt];
    if (p.count < 5) return;
    float frac = [p[0] floatValue];
    NSString *msg = p[1], *detail = p[2];
    BOOL done = [p[3] isEqualToString:@"1"];
    NSString *err = [[p subarrayWithRange:NSMakeRange(4, p.count - 4)] componentsJoinedByString:@"|"];
    if (err.length) {
        [timer invalidate];
        [self showError:err];
        return;
    }
    [self setStatus:msg detail:detail progress:frac];
    if (done) {
        [timer invalidate];
        [self showLogin];
    }
}

// Tells the game the size of its screen and the safe area (camera cut-out, rounded corners, home bar, a fold), in pixels. The game keeps its
// on-screen items inside the safe area and lays out for the new shape. 
// When the size or safe area changes while playing (rotation, fold, Stage Manager), the touch controls are laid out again as well.
- (void)pushScreenMetrics:(BOOL)force {
    UIScreen *scr = [UIScreen mainScreen];
    CGFloat k = MIN(scr.scale, 2.0);   // the game view renders at most 2x (patch_sources.py)
    CGRect b = self.controls ? self.controls.bounds : ((self.window && self.window.bounds.size.width > 0) ? self.window.bounds : scr.bounds);
    UIEdgeInsets s = TTAInsets(self.controls ? self.controls.safeAreaInsets : self.window.safeAreaInsets, b);
    NSString *m = [NSString stringWithFormat:@"%.1f,%.1f,%.1f,%.1f,%.1f,%.1f", b.size.width * k, b.size.height * k, s.left * k, s.right * k, s.top * k, s.bottom * k];
    if (!force && [m isEqualToString:self.lastMetrics]) return;
    BOOL playing = self.controls != nil;
    self.lastMetrics = m;
    NSString *code = [NSString stringWithFormat:@"import ios_game\nif hasattr(ios_game, 'set_screen'):\n    ios_game.set_screen(%@)\n", m];
    pyRun(code.UTF8String);
    if (playing && !force) {
        self.controls.hidden = YES;
        self.controls = nil;
        [self showControls];
    }
}

// ----- settings: the same screens as the web app, built from the shared spec ------------------------------------
// The sections, rows and choices come from settings-spec.json (downloaded into <data>/ui with the other launcher files, with a copy inside the
// app as the fallback). A row shows here when its platforms list has "ios" and this app knows what to do with it (see applySetting:value:).

static NSDictionary *ReadSettingsSpec(NSString *dataPath) {
    NSArray *paths = @[[[dataPath stringByAppendingPathComponent:@"ui"] stringByAppendingPathComponent:@"settings-spec.json"],
                       [[[NSBundle mainBundle] resourcePath] stringByAppendingPathComponent:@"settings-spec.json"]];
    for (NSString *p in paths) {
        NSData *d = [NSData dataWithContentsOfFile:p];
        if (!d) continue;
        id j = [NSJSONSerialization JSONObjectWithData:d options:0 error:nil];
        if ([j isKindOfClass:[NSDictionary class]] && [j[@"sections"] isKindOfClass:[NSArray class]]) return j;
    }
    return nil;
}

// row id -> {saved under, default}; the same saved names the web app uses (tta_*)
static NSDictionary<NSString *, NSArray<NSString *> *> *SettingKeys(void) {
    return @{@"picture_quality": @[@"tta_res", @"2"], @"smooth_edges": @[@"tta_aa", @"1"], @"fps": @[@"tta_fps", @"1"],
             @"mix_others": @[@"tta_mix", @"0"], @"touch_ui": @[@"tta_touch", @"auto"]};
}

static NSArray<NSString *> *ImplementedSettings(void) {       // what this app does with each row (picture_quality has no iOS behaviour yet, so it is left out)
    return @[@"smooth_edges", @"fps", @"mix_others", @"touch_ui"];
}

static NSString *SettingValue(NSString *rid) {
    NSArray *k = SettingKeys()[rid];
    NSString *v = [[NSUserDefaults standardUserDefaults] stringForKey:k[0]];
    return v ?: k[1];
}

- (void)applySetting:(NSString *)rid value:(NSString *)v {
    if ([rid isEqualToString:@"fps"]) {
        NSString *code = [NSString stringWithFormat:@"import ios_game\nif hasattr(ios_game, 'set_option'):\n    ios_game.set_option('fps', '%@')\n", v];
        pyRun(code.UTF8String);
    } else if ([rid isEqualToString:@"smooth_edges"]) {
        NSString *code = [NSString stringWithFormat:@"import ios_game\nif hasattr(ios_game, 'set_option'):\n    ios_game.set_option('smooth_edges', '%@')\n", v];
        pyRun(code.UTF8String);
    } else if ([rid isEqualToString:@"mix_others"]) {
        // keep other apps' audio playing (and follow the silent switch), or pause it while the game plays
        [[AVAudioSession sharedInstance] setCategory:([v isEqualToString:@"1"] ? AVAudioSessionCategoryAmbient : AVAudioSessionCategorySoloAmbient) error:nil];
        [[AVAudioSession sharedInstance] setActive:YES error:nil];
    }
    // touch_ui is read by pollUI every quarter second
}

- (void)applyAllSettings {
    for (NSString *rid in ImplementedSettings()) [self applySetting:rid value:SettingValue(rid)];
}

- (void)settingPicked:(UIButton *)b {
    NSArray *parts = [b.accessibilityIdentifier componentsSeparatedByString:@"|"];
    if (parts.count != 2) return;
    NSString *rid = parts[0], *val = parts[1];
    NSArray *k = SettingKeys()[rid];
    if (!k) return;
    [[NSUserDefaults standardUserDefaults] setObject:val forKey:k[0]];
    [self applySetting:rid value:val];
    for (UIView *sib in b.superview.subviews) {                      // the chosen choice is filled, the others are plain
        if (![sib isKindOfClass:[UIButton class]]) continue;
        BOOL on = [sib isEqual:b];
        sib.backgroundColor = on ? [UIColor colorWithRed:0.38 green:0.58 blue:0.95 alpha:1] : [UIColor colorWithRed:0.92 green:0.95 blue:1 alpha:1];
        [(UIButton *)sib setTitleColor:(on ? [UIColor whiteColor] : [UIColor colorWithRed:0.1 green:0.2 blue:0.45 alpha:1]) forState:UIControlStateNormal];
    }
    if ([rid isEqualToString:@"smooth_edges"]) {
        UILabel *note = (UILabel *)[self.settingsWindow.rootViewController.view viewWithTag:7771];
        note.hidden = NO;
    }
}

- (void)closeSettings {
    self.settingsWindow.hidden = YES;
    self.settingsWindow = nil;
}

- (void)openSettings {
    if (self.settingsWindow) return;
    NSString *dp = [self dataPath];
    RegisterToonFont(dp);
    NSDictionary *spec = ReadSettingsSpec(dp);
    CGRect sb = SceneBounds();
    UIWindow *w = NewWindow([UIWindow class], sb);
    w.windowLevel = UIWindowLevelAlert + 10;
    w.backgroundColor = [UIColor clearColor];
    UIViewController *vc = [UIViewController new];
    vc.view.backgroundColor = [UIColor colorWithRed:0.03 green:0.08 blue:0.2 alpha:0.58];
    w.rootViewController = vc;
    CGFloat sc = UIScale();
    UIEdgeInsets safe = w.safeAreaInsets;
    CGFloat cw = MIN(sb.size.width - 2 * MAX(MAX(safe.left, safe.right), 16), 560 * sc);
    CGFloat ch = sb.size.height - 2 * MAX(MAX(safe.top, safe.bottom), 14);
    UIView *card = [[UIView alloc] initWithFrame:CGRectMake((sb.size.width - cw) / 2, (sb.size.height - ch) / 2, cw, ch)];
    card.backgroundColor = [UIColor colorWithRed:0.97 green:0.98 blue:1 alpha:0.98];
    card.layer.cornerRadius = 22;
    card.layer.borderWidth = 4;
    card.layer.borderColor = [UIColor colorWithRed:0.12 green:0.30 blue:0.65 alpha:1].CGColor;
    card.clipsToBounds = YES;
    [vc.view addSubview:card];
    UIColor *ink = [UIColor colorWithRed:0.1 green:0.2 blue:0.45 alpha:1], *soft = [UIColor colorWithRed:0.30 green:0.36 blue:0.55 alpha:1];

    UILabel *title = [[UILabel alloc] initWithFrame:CGRectMake(0, 12 * sc, cw, 40 * sc)];
    title.text = spec[@"title"] ?: @"Settings";
    title.textAlignment = NSTextAlignmentCenter;
    title.font = ToonFont(30 * sc);
    title.textColor = ink;
    [card addSubview:title];
    UIButton *done = [self pillButton:@"Done" frame:CGRectMake((cw - 150 * sc) / 2, ch - 46 * sc - 12 * sc, 150 * sc, 46 * sc)
                                 fill:[UIColor colorWithRed:1 green:0.851 blue:0.149 alpha:1] text:[UIColor colorWithRed:0.45 green:0.22 blue:0.02 alpha:1] size:22 * sc];
    done.layer.borderColor = [UIColor colorWithRed:0.45 green:0.22 blue:0.02 alpha:1].CGColor;
    [done addTarget:self action:@selector(closeSettings) forControlEvents:UIControlEventTouchUpInside];
    [card addSubview:done];
    UIScrollView *sv = [[UIScrollView alloc] initWithFrame:CGRectMake(0, 56 * sc, cw, ch - 56 * sc - 70 * sc)];
    [card addSubview:sv];

    CGFloat y = 4 * sc, pad = 22 * sc;
    for (NSDictionary *sec in spec[@"sections"]) {
        NSMutableArray *rows = [NSMutableArray array];
        for (NSDictionary *r in sec[@"rows"]) {
            NSArray *pl = r[@"platforms"];
            if (pl && ![pl containsObject:@"ios"]) continue;
            if (r[@"type"] || ![ImplementedSettings() containsObject:r[@"id"]]) continue;
            [rows addObject:r];
        }
        if (!rows.count) continue;
        UILabel *h = [[UILabel alloc] initWithFrame:CGRectMake(pad, y, cw - 2 * pad, 24 * sc)];
        h.text = [(NSString *)sec[@"title"] uppercaseString];
        h.font = ToonFont(15 * sc);
        h.textColor = ink;
        [sv addSubview:h];
        y += 28 * sc;
        for (NSDictionary *r in rows) {
            NSString *rid = r[@"id"];
            NSArray *choices = r[@"choices"];
            CGFloat bh = 32 * sc, gap = 8 * sc, total = 0;
            NSMutableArray *widths = [NSMutableArray array];
            for (NSArray *c in choices) {
                CGFloat bw = MAX(58 * sc, [(NSString *)c[1] length] * 9.5 * sc + 30 * sc);
                [widths addObject:@(bw)];
                total += bw + gap;
            }
            total -= gap;
            BOOL stack = total > (cw - 2 * pad) * 0.52;                 // too wide to share a line with the label: choices go on their own line
            UILabel *l = [[UILabel alloc] initWithFrame:CGRectMake(pad, y, stack ? cw - 2 * pad : (cw - 2 * pad) - total - 12 * sc, 22 * sc)];
            l.text = r[@"label"];
            l.font = ToonFont(17 * sc);
            l.textColor = ink;
            l.adjustsFontSizeToFitWidth = YES;
            l.minimumScaleFactor = 0.6;
            [sv addSubview:l];
            if (r[@"hint"]) {
                UILabel *hl = [[UILabel alloc] initWithFrame:CGRectMake(pad, y + 22 * sc, stack ? cw - 2 * pad : (cw - 2 * pad) - total - 12 * sc, 34 * sc)];
                hl.text = r[@"hint"];
                hl.font = [UIFont systemFontOfSize:11 * sc weight:UIFontWeightMedium];
                hl.textColor = soft;
                hl.numberOfLines = 2;
                [sv addSubview:hl];
            }
            CGFloat by = stack ? y + 58 * sc : y + 2 * sc;
            UIView *group = [[UIView alloc] initWithFrame:CGRectMake(stack ? pad : cw - pad - total, by, total, bh)];
            NSString *cur = SettingValue(rid);
            CGFloat x = 0;
            for (NSUInteger i = 0; i < choices.count; i++) {
                NSArray *c = choices[i];
                BOOL on = [c[0] isEqualToString:cur];
                UIButton *b = [self pillButton:c[1] frame:CGRectMake(x, 0, [widths[i] doubleValue], bh)
                                          fill:(on ? [UIColor colorWithRed:0.38 green:0.58 blue:0.95 alpha:1] : [UIColor colorWithRed:0.92 green:0.95 blue:1 alpha:1])
                                          text:(on ? [UIColor whiteColor] : ink) size:15 * sc];
                b.layer.cornerRadius = 12;
                b.layer.borderWidth = 2;
                b.accessibilityIdentifier = [NSString stringWithFormat:@"%@|%@", rid, c[0]];
                [b addTarget:self action:@selector(settingPicked:) forControlEvents:UIControlEventTouchUpInside];
                [group addSubview:b];
                x += [widths[i] doubleValue] + gap;
            }
            [sv addSubview:group];
            y = by + bh + 6 * sc;
            if (r[@"restart_note"]) {
                UILabel *n = [[UILabel alloc] initWithFrame:CGRectMake(pad, y, cw - 2 * pad, 18 * sc)];
                n.text = r[@"restart_note"];
                n.font = [UIFont systemFontOfSize:12 * sc weight:UIFontWeightSemibold];
                n.textColor = [UIColor colorWithRed:0.7 green:0.35 blue:0.05 alpha:1];
                n.textAlignment = NSTextAlignmentRight;
                n.hidden = YES;
                n.tag = 7771;
                [sv addSubview:n];
                y += 22 * sc;
            }
            y += 14 * sc;
        }
        y += 6 * sc;
    }
    if (!spec) {
        UILabel *e = [[UILabel alloc] initWithFrame:CGRectMake(pad, y, cw - 2 * pad, 40 * sc)];
        e.text = @"The settings list could not be read.";
        e.font = ToonFont(16 * sc);
        e.textColor = ink;
        [sv addSubview:e];
        y += 44 * sc;
    }
    sv.contentSize = CGSizeMake(cw, y + 8 * sc);
    self.settingsWindow = w;
    [w makeKeyAndVisible];
}

- (void)launchGameWithCookie:(NSString *)cookie {
    CrashMarkerSet();                      // cleared again once the game has run for a few seconds (see tick:)
    [self pushScreenMetrics:YES];
    [self applySetting:@"smooth_edges" value:SettingValue(@"smooth_edges")];
    [self setupLog];
    fprintf(stderr, "LAUNCH BEGIN%c", 10);
    {
        NSError *e1 = nil, *e2 = nil;
        AVAudioSession *as = [AVAudioSession sharedInstance];
        BOOL c = [as setCategory:AVAudioSessionCategoryPlayback error:&e1];
        BOOL a = [as setActive:YES error:&e2];
        AVAudioSessionPortDescription *o = as.currentRoute.outputs.firstObject;
        fprintf(stderr, "AUDIO SESSION category=%d active=%d err=%s / %s route=%s rate=%.0f\n", c, a, e1.localizedDescription.UTF8String ?: "-", e2.localizedDescription.UTF8String ?: "-", o.portType.UTF8String ?: "none", as.sampleRate);
    }
    NSString *code = [NSString stringWithFormat:
        @"try:\n"
         "    import ios_game\n"
         "    ios_game.launch('%@', '%@', '%@', '%@', '%@')\n"
         "    _g = 'LAUNCH OK'\n"
         "except BaseException:\n"
         "    import traceback\n"
         "    _g = 'LAUNCH FAIL ' + chr(10).join(traceback.format_exc().strip().splitlines()[-8:])\n",
        [self dataPath], [self fwPath], self.serverGame, cookie, [[self resPath] stringByAppendingPathComponent:@"."]];
    NSString *g = pyString(code.UTF8String, "_g");
    fprintf(stderr, "LAUNCH RESULT: %s%c", g.UTF8String, 10);
    if ([g hasPrefix:@"LAUNCH OK"]) {
        self.link = [CADisplayLink displayLinkWithTarget:self selector:@selector(tick:)];
        // up to the screen's top rate (120 Hz on ProMotion iPhones and iPads; the Info.plist key CADisableMinimumFrameDurationOnPhone lets an
        // iPhone go above 60). The system picks the highest rate in 60..120 that the game keeps up with, so a heavy scene drops to 60 instead of stuttering.
        if (@available(iOS 15.0, *)) {
            self.link.preferredFrameRateRange = CAFrameRateRangeMake(60, 60, 60);      // starts at 60; tick: raises it while frames are cheap enough
        }
        [self.link addToRunLoop:[NSRunLoop mainRunLoop] forMode:NSRunLoopCommonModes];
        fprintf(stderr, "DISPLAY maxFPS=%ld\n", (long)[UIScreen mainScreen].maximumFramesPerSecond);
        [self.spinner stopAnimating];
        // the game draws into this window now: take the start-screen art out of the way
        [self.bgView removeFromSuperview];
        [self.logoView removeFromSuperview];
        self.bgView = nil;
        self.logoView = nil;
        self.gradient.hidden = YES;
        for (UIView *f in self.fallbackViews) f.hidden = YES;
        self.statusLabel.hidden = YES;
        self.detailLabel.hidden = YES;
        self.bar.hidden = YES;
        [UIApplication sharedApplication].idleTimerDisabled = YES;   // do not dim or lock mid-game
        [self showControls];
        [self applyAllSettings];
        self.alContext = alcGetCurrentContext();
        fprintf(stderr, "AUDIO CONTEXT %p\n", self.alContext);
        // Opening or closing a two-screen phone changes the size of the app's window while it runs. The game's own window holds its view at a fixed size,
        // so it never followed: let it (and its view) resize with the window; the game view then tells the engine its new size.
        for (UIWindow *pw in gScene.windows) {
            if (pw == self.window || pw == self.controls) continue;
            for (UIView *v in pw.subviews) {
                v.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
                for (UIView *sv in v.subviews) sv.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
            }
            fprintf(stderr, "GAME WINDOW %s frame %s subviews %lu\n", NSStringFromClass([pw class]).UTF8String, NSStringFromCGRect(pw.frame).UTF8String, (unsigned long)pw.subviews.count);
        }
        {
            UIScreen *ms = [UIScreen mainScreen];
            fprintf(stderr, "GEOMETRY main=%s scale=%.2f native=%s | scene=%s sceneScreen=%s scale=%.2f | window=%s controls=%s safe=%s\n",
                    NSStringFromCGRect(ms.bounds).UTF8String, ms.scale, NSStringFromCGRect(ms.nativeBounds).UTF8String,
                    NSStringFromCGRect(gScene.coordinateSpace.bounds).UTF8String, NSStringFromCGRect(gScene.screen.bounds).UTF8String, gScene.screen.scale,
                    NSStringFromCGRect(self.window.bounds).UTF8String, NSStringFromCGRect(self.controls.bounds).UTF8String,
                    NSStringFromUIEdgeInsets(self.window.safeAreaInsets).UTF8String);
        }
        self.window.hidden = YES;   // the game has its own window underneath: do not cover it
    } else {
        [self showError:g];
    }
}

- (void)tick:(CADisplayLink *)link {
    CFTimeInterval t0 = CACurrentMediaTime();
    pyRun("import ios_game\nios_game.step()\n");
    static double stepEma = 0.016;                       // how long a frame's work takes (smoothed): the display rate follows it
    stepEma += ((CACurrentMediaTime() - t0) - stepEma) * 0.05;
    if ((++self.frameTick % 20) == 0) [self pushScreenMetrics:NO];
    if (self.frameTick == 300) CrashMarkerClear();      // the game ran for a few seconds: this start did not crash
    if (@available(iOS 15.0, *)) {
        if ((self.frameTick % 90) == 0) {
            // 120 only while a frame's work fits well inside 8.3 ms, 90 inside 11 ms, otherwise 60: a heavy scene steps down instead of stuttering
            float want = stepEma < 0.0065 ? 120 : (stepEma < 0.0095 ? 90 : 60);
            if (want != self.link.preferredFrameRateRange.preferred) {
                self.link.preferredFrameRateRange = CAFrameRateRangeMake(60, want, want);
                fprintf(stderr, "DISPLAY rate %.0f (frame work %.1f ms)\n", want, stepEma * 1000.0);
            }
        }
    }
    if ((self.frameTick % 60) == 0 && self.alContext && !alcGetCurrentContext() && [UIApplication sharedApplication].applicationState == UIApplicationStateActive) {
        fprintf(stderr, "AUDIO CONTEXT LOST: restoring\n");      // an interruption that never ended left the sound without a context (every sound call then failed)
        [self resumeAudio];
    }
     // a few times a second is plenty for a rotation or a fold
}

// ----- controls and log overlay -------------------------------------------------------------

- (void)showControls {
    // size from the app's own window, not UIScreen: on a two-screen phone (iPhone Duo) the main screen is not what the app is drawn into
    CGRect b = (self.window && self.window.bounds.size.width > 0) ? self.window.bounds : SceneBounds();
    UIEdgeInsets safe = TTAInsets(self.window.safeAreaInsets, b);
    self.controls = NewWindow([PassThroughWindow class], b);
    self.controls.windowLevel = UIWindowLevelAlert;
    self.controls.backgroundColor = [UIColor clearColor];
    UIViewController *vc = [TTAEdgeViewController new];
    vc.view.backgroundColor = [UIColor clearColor];
    self.controls.rootViewController = vc;

    // the buttons follow the window's height (they were sized for a ~430 pt tall phone window): smaller on a short window, the old iPad size on a tall one
    CGFloat sc = MAX(0.7, MIN(b.size.height / 430.0, 1.45));
    CGFloat js = 150 * sc;
    JoystickView *joy = [[JoystickView alloc] initWithFrame:CGRectMake(MAX(safe.left, 24) + 20 * sc, b.size.height - js - MAX(safe.bottom, 16) - 24 * sc, js, js)];
    [vc.view addSubview:joy];
    CGFloat jb = 92 * sc;
    CGRect jf = CGRectMake(b.size.width - jb - MAX(safe.right, 24) - 30 * sc, b.size.height - jb - MAX(safe.bottom, 16) - 130 * sc, jb, jb);
    JumpButton *jump = [[JumpButton alloc] initWithFrame:jf];
    [vc.view addSubview:jump];
    CGFloat cb = 58 * sc;
    PadButton *cam = [[PadButton alloc] initWithFrame:CGRectMake(jf.origin.x + (jb - cb) / 2, jf.origin.y - cb - 16 * sc, cb, cb) kind:@"camera" title:@"CAM"];
    [vc.view addSubview:cam];
    self.joyView = joy;
    self.hudViews = @[joy, jump, cam];
    for (UIView *hv in self.hudViews) hv.hidden = YES;   // shown by pollUI once the player is in the world
    self.actionButton = [[PadButton alloc] initWithFrame:CGRectMake(jf.origin.x - jb - 20 * sc, jf.origin.y, jb, jb) kind:@"action" title:@"ACTION"];
    self.actionButton.hidden = YES;
    [vc.view addSubview:self.actionButton];
    // tug-of-war: two big tap buttons (the game needs fast alternating left/right presses)
    CGFloat pb = 112 * sc;
    CGFloat py = b.size.height - pb - MAX(safe.bottom, 16) - 20 * sc;
    self.padLeft = [[PadButton alloc] initWithFrame:CGRectMake(b.size.width / 2 - pb - 14 * sc, py, pb, pb) kind:@"padleft" title:@"\u25C0"];
    self.padRight = [[PadButton alloc] initWithFrame:CGRectMake(b.size.width / 2 + 14 * sc, py, pb, pb) kind:@"padright" title:@"\u25B6"];
    self.padLeft.hidden = YES;
    self.padRight.hidden = YES;
    [vc.view addSubview:self.padLeft];
    [vc.view addSubview:self.padRight];
    // invisible text field: the iOS keyboard types into the game's focused chat box through it
    self.kbField = [[UITextField alloc] initWithFrame:CGRectMake(0, 0, 2, 2)];
    self.kbField.alpha = 0.02;
    self.kbField.autocorrectionType = UITextAutocorrectionTypeNo;
    self.kbField.autocapitalizationType = UITextAutocapitalizationTypeSentences;
    self.kbField.returnKeyType = UIReturnKeySend;
    self.kbField.delegate = (id<UITextFieldDelegate>)self;
    [self.kbField addTarget:self action:@selector(kbChanged:) forControlEvents:UIControlEventEditingChanged];
    [vc.view addSubview:self.kbField];
    self.uiPoll = [NSTimer scheduledTimerWithTimeInterval:0.25 target:self selector:@selector(pollUI:) userInfo:nil repeats:YES];
    if (gScene != nil && gScene.screen.bounds.size.width > [UIScreen mainScreen].bounds.size.width + 1.0 && self.serverRes) {
        NSString *logPath = [[self docsPath] stringByAppendingPathComponent:@"tta_log.txt"];
        NSString *server = self.serverRes;
        [NSTimer scheduledTimerWithTimeInterval:15.0 repeats:YES block:^(NSTimer *t) {
            NSString *send = [NSString stringWithFormat:@"try:\n    import ios_game\n    ios_game.live_log('%@', '%@')\nexcept BaseException:\n    pass\n", server, logPath];
            pyRun(send.UTF8String);
        }];
    }

    UIView *hot = [[UIView alloc] initWithFrame:CGRectMake(b.size.width / 2 - 50, 0, 100, 40)];   // top centre: nothing in the game lives here
    hot.backgroundColor = [UIColor clearColor];
    UITapGestureRecognizer *five = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(toggleLog)];
    five.numberOfTapsRequired = 5;
    [hot addGestureRecognizer:five];
    [vc.view addSubview:hot];
    UIButton *cog = [UIButton buttonWithType:UIButtonTypeCustom];
    CGFloat cs = 30 * sc;
    cog.frame = CGRectMake(MAX(safe.left, 6) + 150 * sc, MAX(safe.top, 6), cs, cs);   // top-left, beside the two chat buttons: clear of the friends button and of the Pick-a-Toon title
    cog.backgroundColor = [UIColor colorWithRed:0.10 green:0.26 blue:0.62 alpha:0.62];
    cog.layer.cornerRadius = cs / 2;
    cog.layer.borderWidth = 1.5;
    cog.layer.borderColor = [UIColor colorWithRed:0.85 green:0.92 blue:1 alpha:0.9].CGColor;
    UIImage *gear = [UIImage systemImageNamed:@"gearshape.fill" withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:cs * 0.55]];
    [cog setImage:[gear imageWithTintColor:[UIColor whiteColor] renderingMode:UIImageRenderingModeAlwaysOriginal] forState:UIControlStateNormal];
    [cog addTarget:self action:@selector(openSettings) forControlEvents:UIControlEventTouchUpInside];
    [vc.view addSubview:cog];
    if (gScene != nil && gScene.screen.bounds.size.width > [UIScreen mainScreen].bounds.size.width + 1.0) {
        // A two-screen phone (the iPhone Duo): taps at the right-hand edge never reached the game's own friends list and sticker book buttons, so
        // here are two native buttons in the top-left corner, where taps work, that press the game's buttons.
        NSArray *symbols = @[@"person.2.fill", @"book.closed.fill"];
        NSMutableArray *sbs = [NSMutableArray array];
        CGFloat bs = 40 * sc;
        for (int i = 0; i < 2; i++) {
            UIButton *b2 = [UIButton buttonWithType:UIButtonTypeCustom];
            b2.frame = CGRectMake(cog.frame.origin.x + cs + 10 * sc + i * (bs + 10 * sc), cog.frame.origin.y + (cs - bs) / 2, bs, bs);
            b2.backgroundColor = [UIColor colorWithRed:0.10 green:0.26 blue:0.62 alpha:0.78];
            b2.layer.cornerRadius = bs / 2;
            b2.layer.borderWidth = 1.5;
            b2.layer.borderColor = [UIColor colorWithRed:0.85 green:0.92 blue:1 alpha:0.9].CGColor;
            UIImage *im = [UIImage systemImageNamed:symbols[i] withConfiguration:[UIImageSymbolConfiguration configurationWithPointSize:bs * 0.5]];
            [b2 setImage:[im imageWithTintColor:[UIColor whiteColor] renderingMode:UIImageRenderingModeAlwaysOriginal] forState:UIControlStateNormal];
            b2.tag = i + 1;
            b2.hidden = YES;
            [b2 addTarget:self action:@selector(hotTapped:) forControlEvents:UIControlEventTouchUpInside];
            [vc.view addSubview:b2];
            [sbs addObject:b2];
        }
        self.hotButtons = sbs;
        self.hotspots = YES;
    }
    self.controls.hidden = NO;
    // the key window's controller is the one iOS asks about edge gestures: the game's own window has none, so this one is key (it passes every tap it does not use on)
    [self.controls makeKeyWindow];
    [vc setNeedsUpdateOfScreenEdgesDeferringSystemGestures];
    fprintf(stderr, "EDGES deferring=%lu key=%d\n", (unsigned long)vc.preferredScreenEdgesDeferringSystemGestures, self.controls.isKeyWindow);
}

- (void)kbChanged:(UITextField *)f {
    NSString *t = [[f.text stringByReplacingOccurrencesOfString:@"\\" withString:@""] stringByReplacingOccurrencesOfString:@"'" withString:@"\\'"];
    t = [t stringByReplacingOccurrencesOfString:@"\n" withString:@" "];
    NSString *code = [NSString stringWithFormat:@"import ios_game\nios_game.ui_text_set('%@')\n", t];
    pyRun(code.UTF8String);
}

- (void)pollUI:(NSTimer *)timer {
    NSString *r = pyString("import ios_game\n_ui = str(ios_game.ui_controls_visible()) + '|' + str(ios_game.ui_action_available()) + '|' + str(ios_game.ui_tug_active()) + '|' + ios_game.ui_text_state()\n", "_ui");
    NSArray *p = [r componentsSeparatedByString:@"|"];
    if (p.count < 5) return;
    BOOL vis = [p[0] isEqualToString:@"1"];
    if (self.hudWasVisible && !vis) {
        [self.joyView reset];      // a finger still on the joystick must not keep the toon running
        [self.actionButton setDown:NO];
        [self.padLeft setDown:NO];
        [self.padRight setDown:NO];
    }
    self.hudWasVisible = vis;
    BOOL hideTouch = [SettingValue(@"touch_ui") isEqualToString:@"hide"];
    for (UIView *hv in self.hudViews) hv.hidden = !vis || hideTouch;
    self.actionButton.hidden = !vis || hideTouch || ![p[1] isEqualToString:@"1"];
    BOOL tug = vis && !hideTouch && [p[2] isEqualToString:@"1"];
    self.padLeft.hidden = !tug;
    self.padRight.hidden = !tug;
    BOOL focus = [p[3] isEqualToString:@"1"];
    if (focus && !self.kbActive) {
        NSString *text = [[p subarrayWithRange:NSMakeRange(4, p.count - 4)] componentsJoinedByString:@"|"];
        self.kbField.text = text;
        self.kbActive = YES;
        [self.controls makeKeyWindow];
        [self.kbField becomeFirstResponder];
    } else if (!focus && self.kbActive) {
        [self.kbField resignFirstResponder];
        self.kbActive = NO;
    }
    for (UIButton *hb in self.hotButtons) hb.hidden = !vis;      // the two-screen phone's Friends and Book buttons (see showControls)
}

- (void)hotTapped:(UIButton *)sender {
    pyRun(sender.tag == 1 ? "import ios_game\nios_game.ui_press('friends')\n" : "import ios_game\nios_game.ui_press('book')\n");
}

- (void)audioInterrupted:(NSNotification *)n {
    NSUInteger type = [n.userInfo[AVAudioSessionInterruptionTypeKey] unsignedIntegerValue];
    fprintf(stderr, "AUDIO INTERRUPTION type=%lu reason=%s\n", (unsigned long)type, [[n.userInfo[AVAudioSessionInterruptionReasonKey] description] UTF8String] ?: "-");
    if (type == AVAudioSessionInterruptionTypeBegan) {
        ALCcontext *c = alcGetCurrentContext();
        if (c) self.alContext = c;
        alcMakeContextCurrent(NULL);
        if (self.alContext) alcSuspendContext(self.alContext);
    } else {
        [self resumeAudio];
    }
}

- (void)resumeAudio {
    [[AVAudioSession sharedInstance] setActive:YES error:nil];
    if (self.alContext) {
        alcMakeContextCurrent(self.alContext);
        alcProcessContext(self.alContext);
    }
}

- (void)applicationWillResignActive:(UIApplication *)application {
    // no OpenGL work while the app is in the background (iOS would terminate it)
    self.link.paused = YES;
    pyRun("import ios_game\nios_game.ui_move(0,0,0,0)\n");
}

- (void)applicationDidBecomeActive:(UIApplication *)application {
    self.link.paused = NO;
    [self resumeAudio];
}

- (void)setupLog {
    NSString *logPath = [[self docsPath] stringByAppendingPathComponent:@"tta_log.txt"];
    freopen(logPath.UTF8String, "a", stdout);
    freopen(logPath.UTF8String, "a", stderr);
    setvbuf(stdout, NULL, _IOLBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
}

- (void)toggleLog {
    NSString *logPath = [[self docsPath] stringByAppendingPathComponent:@"tta_log.txt"];
    if ((!self.logWindow || self.logWindow.hidden) && self.serverRes) {      // opening the log also sends it to the server, so a problem on a phone can be read there
        NSString *send = [NSString stringWithFormat:@"try:\n    import ios_game\n    ios_game.send_crash_report('%@', '%@', 'MANUAL ')\nexcept BaseException:\n    pass\n", self.serverRes, logPath];
        pyRun(send.UTF8String);
    }
    if (self.logWindow) {
        self.logWindow.hidden = !self.logWindow.hidden;
        return;
    }
    self.logWindow = NewWindow([UIWindow class], CGRectMake(0, 0, SceneBounds().size.width, 330));
    self.logWindow.windowLevel = UIWindowLevelAlert + 10;
    self.logWindow.userInteractionEnabled = NO;
    self.logWindow.backgroundColor = [UIColor colorWithWhite:0 alpha:0.6];
    self.logView = [[UITextView alloc] initWithFrame:self.logWindow.bounds];
    self.logView.backgroundColor = [UIColor clearColor];
    self.logView.textColor = [UIColor greenColor];
    self.logView.font = [UIFont fontWithName:@"Menlo" size:9];
    self.logView.editable = NO;
    [self.logWindow addSubview:self.logView];
    self.logWindow.hidden = NO;
    self.logTimer = [NSTimer scheduledTimerWithTimeInterval:1.0 repeats:YES block:^(NSTimer *t) {
        if (self.logWindow.hidden) return;
        NSData *d = [NSData dataWithContentsOfFile:logPath];
        if (d.length > 4200) d = [d subdataWithRange:NSMakeRange(d.length - 4200, 4200)];
        NSString *str = [[NSString alloc] initWithData:d encoding:NSUTF8StringEncoding] ?: @"";
        self.logView.text = str;
        [self.logView scrollRangeToVisible:NSMakeRange(str.length > 0 ? str.length - 1 : 0, 1)];
    }];
}

// ----- app lifecycle ------------------------------------------------------------------------

- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)launchOptions {
    // "Playback" ignores the phone's silent switch; the game's own sound options (Shticker Book) still apply
    [[AVAudioSession sharedInstance] setCategory:AVAudioSessionCategoryPlayback error:nil];
    [[AVAudioSession sharedInstance] setActive:YES error:nil];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(audioInterrupted:) name:AVAudioSessionInterruptionNotification object:nil];
    [self loadServerChoice];   // before the art, so the cached start screen belongs to the right server
    return YES;
}

- (UISceneConfiguration *)application:(UIApplication *)application configurationForConnectingSceneSession:(UISceneSession *)connectingSceneSession options:(UISceneConnectionOptions *)options {
    UISceneConfiguration *c = [[UISceneConfiguration alloc] initWithName:@"Default Configuration" sessionRole:connectingSceneSession.role];
    c.delegateClass = [SceneDelegate class];
    return c;
}

// the window scene has connected: build the first window and start Python (what used to happen in didFinishLaunching)
- (void)beginInScene:(UIWindowScene *)scene {
    if (self.window) return;
    gScene = scene;
    self.window = NewWindow([UIWindow class], SceneBounds());
    UIViewController *vc = [TTAEdgeViewController new];
    vc.view = [self buildSplash:SceneBounds()];
    self.window.rootViewController = vc;
    [self.window makeKeyAndVisible];
    [self applyArt];   // cached art from an earlier launch, so the placeholder never flashes
    [self.spinner startAnimating];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.4 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
        self.report = [self startPython];
        if ([self.report containsString:@"FAIL"] || [self.report containsString:@"failed"]) {
            [self showError:self.report];
            return;
        }
        [self.spinner stopAnimating];
        BOOL twoScreens = (gScene != nil && gScene.screen != [UIScreen mainScreen]);
        if ((gSendPrevLog || (gHavePrevLog && twoScreens)) && self.serverRes) {
            NSString *tag = gSendPrevLog ? @"" : @"PREV ";      // a crash report, or (two-screen phones only) the end of the last normal run
            gSendPrevLog = NO;
            gHavePrevLog = NO;
            NSString *send = [NSString stringWithFormat:@"try:\n    import ios_game\n    ios_game.send_crash_report('%@', '%s', '%@')\nexcept BaseException:\n    pass\n", self.serverRes, gPrevLogPath, tag];
            pyRun(send.UTF8String);
        }
        if (self.serverRes) [self beginDownload];
        else [self showServerChoiceCanGoBack:NO];
    });
}

- (UIInterfaceOrientationMask)application:(UIApplication *)application supportedInterfaceOrientationsForWindow:(UIWindow *)window {
    return UIInterfaceOrientationMaskLandscape;
}

@end

@implementation SceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)connectionOptions {
    if (![scene isKindOfClass:[UIWindowScene class]]) return;
    self.window = ((AppDelegate *)[UIApplication sharedApplication].delegate).window;
    [(AppDelegate *)[UIApplication sharedApplication].delegate beginInScene:(UIWindowScene *)scene];
    self.window = ((AppDelegate *)[UIApplication sharedApplication].delegate).window;
}
@end

int main(int argc, char *argv[]) {
    @autoreleasepool {
        InstallCrashHandlers();
        return UIApplicationMain(argc, argv, NSStringFromClass([TTAApplication class]), NSStringFromClass([AppDelegate class]));
    }
}
