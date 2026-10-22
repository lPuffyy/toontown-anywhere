// Toontown for iPhone: native shell around the real TTR-Offline client (Panda3D + embedded Python).
//  - branded loading screen with download progress
//  - starts the game, then overlays touch controls (joystick, jump)
//  - 5 taps in the top-left corner toggles the developer log overlay
#import <UIKit/UIKit.h>
#import <Security/Security.h>
#import <AVFoundation/AVFoundation.h>
#import <OpenAL/alc.h>
#import <QuartzCore/QuartzCore.h>
#import <CommonCrypto/CommonDigest.h>
#include <Python.h>

#import "ttr_config.h"   // RESOURCE_SERVER and GAME_SERVER, generated at build time

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

static CGFloat UIScale(void) {
    return UI_USER_INTERFACE_IDIOM() == UIUserInterfaceIdiomPad ? 1.45 : 1.0;
}

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
        l.font = [UIFont fontWithName:@"MarkerFelt-Wide" size:frame.size.width * 0.26] ?: [UIFont boldSystemFontOfSize:frame.size.width * 0.26];
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
        l.font = [UIFont fontWithName:@"MarkerFelt-Wide" size:20] ?: [UIFont boldSystemFontOfSize:20];
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

@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property (strong, nonatomic) UIWindow *window;
@property (strong, nonatomic) CADisplayLink *link;
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
// in-game touch helpers
@property (strong, nonatomic) PadButton *actionButton;
@property (strong, nonatomic) NSArray<UIView *> *hudViews;
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

@implementation AppDelegate

- (NSString *)resPath { return [[NSBundle mainBundle] resourcePath]; }
- (NSString *)fwPath { return [[self resPath] stringByAppendingPathComponent:@"Frameworks"]; }
- (NSString *)docsPath {
    return NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES).firstObject;
}

// ----- loading screen ------------------------------------------------------------------------

- (UIView *)buildSplash:(CGRect)bounds {
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

    UIFont *title = [UIFont fontWithName:@"MarkerFelt-Wide" size:84] ?: [UIFont boldSystemFontOfSize:84];
    UILabel *t = [[UILabel alloc] init];
    t.text = @"TOONTOWN: ANYWHERE";
    t.adjustsFontSizeToFitWidth = YES;
    t.minimumScaleFactor = 0.5;
    t.font = title;
    t.textColor = [UIColor colorWithRed:1.0 green:0.85 blue:0.15 alpha:1];
    t.layer.shadowColor = [UIColor blackColor].CGColor;
    t.layer.shadowOffset = CGSizeMake(0, 5);
    t.layer.shadowOpacity = 0.5;
    t.layer.shadowRadius = 0;
    t.textAlignment = NSTextAlignmentCenter;
    t.frame = CGRectMake(0, bounds.size.height * 0.16, bounds.size.width, 100);
    t.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleBottomMargin;
    [v addSubview:t];
    [fb addObject:t];

    UILabel *sub = [[UILabel alloc] init];
    sub.text = @"Unofficial mobile client";
    sub.font = [UIFont fontWithName:@"MarkerFelt-Thin" size:28] ?: [UIFont systemFontOfSize:28];
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
    self.statusLabel.font = [UIFont fontWithName:@"MarkerFelt-Wide" size:26] ?: [UIFont boldSystemFontOfSize:26];
    self.statusLabel.textColor = [UIColor whiteColor];
    self.statusLabel.text = @"Getting ready...";
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
    if (self.bgView) return;
    NSString *ui = [[self dataPath] stringByAppendingPathComponent:@"ui"];
    UIImage *bg = [UIImage imageWithContentsOfFile:[ui stringByAppendingPathComponent:@"background.jpg"]];
    UIImage *logo = [UIImage imageWithContentsOfFile:[ui stringByAppendingPathComponent:@"logo.png"]];
    if (!bg || !logo) return;
    UIView *root = self.window.rootViewController.view;
    CGRect b = root.bounds;
    self.bgView = [[UIImageView alloc] initWithImage:bg];
    self.bgView.frame = b;
    self.bgView.contentMode = UIViewContentModeScaleAspectFill;
    self.bgView.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [root insertSubview:self.bgView atIndex:0];
    CGFloat lh = MIN(b.size.height * 0.40, 200 * UIScale()), lw = lh * logo.size.width / logo.size.height;
    self.logoView = [[UIImageView alloc] initWithImage:logo];
    self.logoView.frame = CGRectMake((b.size.width - lw) / 2, MAX(b.size.height * 0.04, 10), lw, lh);
    self.logoView.userInteractionEnabled = NO;
    self.bgView.userInteractionEnabled = NO;
    self.logoView.autoresizingMask = UIViewAutoresizingFlexibleLeftMargin | UIViewAutoresizingFlexibleRightMargin | UIViewAutoresizingFlexibleBottomMargin;
    [root insertSubview:self.logoView aboveSubview:self.bgView];
    for (UIView *f in self.fallbackViews) f.hidden = YES;
    self.gradient.hidden = YES;
}

// ----- sign in -------------------------------------------------------------------------------

static NSString *const kService = @"com.ttr.mobile";

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
    NSString *mode = [u stringForKey:@"ttr_srv_mode"];
    if (!mode) {
        // installs from before the picker already hold the default server's files: keep using it
        if ([[NSFileManager defaultManager] fileExistsAtPath:[[self docsPath] stringByAppendingPathComponent:@"resources"]]) mode = @"default";
        else return NO;
    }
    NSString *res = [u stringForKey:@"ttr_srv_res"], *game = [u stringForKey:@"ttr_srv_game"];
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
    return self.serverIsDefault ? @"ttr_user" : [@"ttr_user_" stringByAppendingString:ServerId(self.serverRes, self.serverGame)];
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
    f.font = [UIFont fontWithName:@"MarkerFelt-Wide" size:24 * UIScale()] ?: [UIFont boldSystemFontOfSize:22 * UIScale()];
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
    self.playButton.titleLabel.font = [UIFont fontWithName:@"MarkerFelt-Wide" size:30 * sc] ?: [UIFont boldSystemFontOfSize:28 * sc];
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
    self.loginError.font = [UIFont fontWithName:@"MarkerFelt-Wide" size:17 * sc] ?: [UIFont boldSystemFontOfSize:16 * sc];
    self.loginError.textColor = [UIColor colorWithRed:0.1 green:0.25 blue:0.55 alpha:1];
    self.loginError.text = @"New here? Pick a name and password and tap PLAY!";
    // credit (the app is an unofficial client for TTR-Offline; see THIRD_PARTY_NOTICES in the app bundle)
    UILabel *credit = [[UILabel alloc] initWithFrame:CGRectMake(20, b.size.height - 22 * sc - MAX(self.window.safeAreaInsets.bottom, 4), b.size.width - 40, 18 * sc)];
    credit.text = @"Unofficial client for TTR-Offline • Based on TTR-Offline by RegDogg (Apache 2.0)";
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
    self.loginWindow = [[UIWindow alloc] initWithFrame:[UIScreen mainScreen].bounds];
    self.loginWindow.windowLevel = UIWindowLevelAlert;
    self.loginWindow.backgroundColor = [UIColor clearColor];
    UIViewController *lvc = [UIViewController new];
    lvc.view.backgroundColor = [UIColor clearColor];
    self.loginWindow.rootViewController = lvc;
    self.loginView.frame = lvc.view.bounds;
    [lvc.view addSubview:self.loginView];
    [self.loginWindow makeKeyAndVisible];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(keyboardChange:) name:UIKeyboardWillShowNotification object:nil];
    [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(keyboardChange:) name:UIKeyboardWillHideNotification object:nil];
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

- (void)askRecoverySetupFor:(NSString *)cookie done:(void (^)(void))done {
    UIAlertController *a = [UIAlertController alertControllerWithTitle:@"Forgot-password help"
        message:@"Pick two answers only you will remember. If you ever forget your password, they let you set a new one."
        preferredStyle:UIAlertControllerStyleAlert];
    [a addTextFieldWithConfigurationHandler:^(UITextField *t) { t.placeholder = @"Your nickname"; t.autocorrectionType = UITextAutocorrectionTypeNo; }];
    [a addTextFieldWithConfigurationHandler:^(UITextField *t) { t.placeholder = @"A toon name you made"; t.autocorrectionType = UITextAutocorrectionTypeNo; }];
    [a addAction:[UIAlertAction actionWithTitle:@"Skip for now" style:UIAlertActionStyleCancel handler:^(UIAlertAction *x) { done(); }]];
    [a addAction:[UIAlertAction actionWithTitle:@"Save" style:UIAlertActionStyleDefault handler:^(UIAlertAction *x) {
        NSString *nick = a.textFields[0].text ?: @"", *toon = a.textFields[1].text ?: @"";
        [self recoveryPost:@"/setrecovery" text:[NSString stringWithFormat:@"%@\n%@\n%@", cookie, nick, toon] done:^(NSString *r) {
            if (![r isEqualToString:@"ok"]) {
                UIAlertController *e = [UIAlertController alertControllerWithTitle:@"Not saved" message:r preferredStyle:UIAlertControllerStyleAlert];
                [e addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:^(UIAlertAction *y) { done(); }]];
                [self.loginWindow.rootViewController presentViewController:e animated:YES completion:nil];
            } else done();
        }];
    }]];
    [self.loginWindow.rootViewController presentViewController:a animated:YES completion:nil];
}

- (void)forgotPassword {
    [self.loginWindow endEditing:YES];
    NSString *user = [[self.userField.text stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceCharacterSet]] lowercaseString];
    if (user.length == 0) {
        [self loginMessage:@"Type your toon name above first, then tap Forgot password." bad:YES];
        return;
    }
    UIAlertController *a = [UIAlertController alertControllerWithTitle:@"Reset password"
        message:[NSString stringWithFormat:@"Answer the two questions you saved for %@, then pick a new password.", user]
        preferredStyle:UIAlertControllerStyleAlert];
    [a addTextFieldWithConfigurationHandler:^(UITextField *t) { t.placeholder = @"Your nickname"; t.autocorrectionType = UITextAutocorrectionTypeNo; }];
    [a addTextFieldWithConfigurationHandler:^(UITextField *t) { t.placeholder = @"A toon name you made"; t.autocorrectionType = UITextAutocorrectionTypeNo; }];
    [a addTextFieldWithConfigurationHandler:^(UITextField *t) { t.placeholder = @"New password"; t.secureTextEntry = YES; }];
    [a addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel handler:nil]];
    [a addAction:[UIAlertAction actionWithTitle:@"Reset" style:UIAlertActionStyleDefault handler:^(UIAlertAction *x) {
        NSString *nick = a.textFields[0].text ?: @"", *toon = a.textFields[1].text ?: @"", *pw = a.textFields[2].text ?: @"";
        if ([pw containsString:@"'"] || [pw containsString:@"\\"] || [pw containsString:@":"]) {
            [self loginMessage:@"Please don't use quotes, colons or backslashes." bad:YES];
            return;
        }
        [self loginMessage:@"Checking..." bad:NO];
        [self recoveryPost:@"/recover" text:[NSString stringWithFormat:@"%@\n%@\n%@\n%@", user, nick, toon, pw] done:^(NSString *r) {
            if ([r isEqualToString:@"ok"]) {
                self.passField.text = pw;
                [self loginMessage:@"Password changed! Tap PLAY." bad:NO];
            } else [self loginMessage:r bad:YES];
        }];
    }]];
    [self.loginWindow.rootViewController presentViewController:a animated:YES completion:nil];
}

// ----- server choice -------------------------------------------------------------------------

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
    b.titleLabel.font = [UIFont fontWithName:@"MarkerFelt-Wide" size:size] ?: [UIFont boldSystemFontOfSize:size];
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
    l.font = bold ? ([UIFont fontWithName:@"MarkerFelt-Wide" size:size] ?: [UIFont boldSystemFontOfSize:size]) : [UIFont systemFontOfSize:size weight:UIFontWeightSemibold];
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

    self.serverWindow = [[UIWindow alloc] initWithFrame:[UIScreen mainScreen].bounds];
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
    if (!self.serverScroll) return;
    CGRect kb = [n.userInfo[UIKeyboardFrameEndUserInfoKey] CGRectValue];
    CGRect inView = [self.serverScroll convertRect:kb fromView:nil];
    CGFloat h = MAX(0, CGRectGetMaxY(self.serverScroll.bounds) - inView.origin.y);
    self.serverScroll.contentInset = UIEdgeInsetsMake(0, 0, h, 0);
    self.serverScroll.scrollIndicatorInsets = self.serverScroll.contentInset;
    UITextField *ff = self.resField.isFirstResponder ? self.resField : (self.gameField.isFirstResponder ? self.gameField : nil);
    if (ff && h > 0) [self.serverScroll scrollRectToVisible:[self.serverScroll convertRect:CGRectInset(ff.bounds, 0, -16) fromView:ff] animated:YES];
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
    [u setObject:isDef ? @"default" : @"custom" forKey:@"ttr_srv_mode"];
    if (!isDef) {
        [u setObject:res forKey:@"ttr_srv_res"];
        [u setObject:game forKey:@"ttr_srv_game"];
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

- (void)launchGameWithCookie:(NSString *)cookie {
    [self setupLog];
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
        [self.link addToRunLoop:[NSRunLoop mainRunLoop] forMode:NSRunLoopCommonModes];
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
        self.window.hidden = YES;   // the game has its own window underneath: do not cover it
    } else {
        [self showError:g];
    }
}

- (void)tick:(CADisplayLink *)link {
    pyRun("import ios_game\nios_game.step()\n");
}

// ----- controls and log overlay -------------------------------------------------------------

- (void)showControls {
    CGRect b = [UIScreen mainScreen].bounds;
    UIEdgeInsets safe = self.window.safeAreaInsets;
    self.controls = [[PassThroughWindow alloc] initWithFrame:b];
    self.controls.windowLevel = UIWindowLevelAlert;
    self.controls.backgroundColor = [UIColor clearColor];
    UIViewController *vc = [UIViewController new];
    vc.view.backgroundColor = [UIColor clearColor];
    self.controls.rootViewController = vc;

    CGFloat sc = UIScale();
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

    UIView *hot = [[UIView alloc] initWithFrame:CGRectMake(b.size.width / 2 - 50, 0, 100, 40)];   // top centre: nothing in the game lives here
    hot.backgroundColor = [UIColor clearColor];
    UITapGestureRecognizer *five = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(toggleLog)];
    five.numberOfTapsRequired = 5;
    [hot addGestureRecognizer:five];
    [vc.view addSubview:hot];
    self.controls.hidden = NO;
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
    for (UIView *hv in self.hudViews) hv.hidden = !vis;
    self.actionButton.hidden = !vis || ![p[1] isEqualToString:@"1"];
    BOOL tug = vis && [p[2] isEqualToString:@"1"];
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
}

- (void)audioInterrupted:(NSNotification *)n {
    NSUInteger type = [n.userInfo[AVAudioSessionInterruptionTypeKey] unsignedIntegerValue];
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
    NSString *logPath = [[self docsPath] stringByAppendingPathComponent:@"ttr_log.txt"];
    freopen(logPath.UTF8String, "a", stdout);
    freopen(logPath.UTF8String, "a", stderr);
    setvbuf(stdout, NULL, _IOLBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
}

- (void)toggleLog {
    if (self.logWindow) {
        self.logWindow.hidden = !self.logWindow.hidden;
        return;
    }
    NSString *logPath = [[self docsPath] stringByAppendingPathComponent:@"ttr_log.txt"];
    self.logWindow = [[UIWindow alloc] initWithFrame:CGRectMake(0, 0, [UIScreen mainScreen].bounds.size.width, 330)];
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
    self.window = [[UIWindow alloc] initWithFrame:[UIScreen mainScreen].bounds];
    UIViewController *vc = [UIViewController new];
    vc.view = [self buildSplash:[UIScreen mainScreen].bounds];
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
        if (self.serverRes) [self beginDownload];
        else [self showServerChoiceCanGoBack:NO];
    });
    return YES;
}

- (UIInterfaceOrientationMask)application:(UIApplication *)application supportedInterfaceOrientationsForWindow:(UIWindow *)window {
    return UIInterfaceOrientationMaskLandscape;
}

@end

int main(int argc, char *argv[]) {
    @autoreleasepool {
        return UIApplicationMain(argc, argv, nil, NSStringFromClass([AppDelegate class]));
    }
}
