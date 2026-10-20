// Toontown for iPhone: native shell around the real TTR-Offline client (Panda3D + embedded Python).
//  - branded loading screen with download progress
//  - starts the game, then overlays touch controls (joystick, jump)
//  - 5 taps in the top-left corner toggles the developer log overlay
#import <UIKit/UIKit.h>
#import <Security/Security.h>
#import <QuartzCore/QuartzCore.h>
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
    t.text = @"TTR: MOBILE";
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
    sub.text = @"Toontown on your iPhone";
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
    NSString *ui = [[self docsPath] stringByAppendingPathComponent:@"ui"];
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
    CGFloat lh = MIN(b.size.height * 0.40, 200), lw = lh * logo.size.width / logo.size.height;
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

- (NSString *)keychainPassword {
    NSDictionary *q = @{(__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword, (__bridge id)kSecAttrService: kService,
                        (__bridge id)kSecReturnData: @YES, (__bridge id)kSecMatchLimit: (__bridge id)kSecMatchLimitOne};
    CFTypeRef out = NULL;
    if (SecItemCopyMatching((__bridge CFDictionaryRef)q, &out) != errSecSuccess || !out) return nil;
    return [[NSString alloc] initWithData:(__bridge_transfer NSData *)out encoding:NSUTF8StringEncoding];
}

- (void)saveKeychainPassword:(NSString *)pw {
    NSDictionary *q = @{(__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword, (__bridge id)kSecAttrService: kService};
    SecItemDelete((__bridge CFDictionaryRef)q);
    NSMutableDictionary *a = [q mutableCopy];
    a[(__bridge id)kSecValueData] = [pw dataUsingEncoding:NSUTF8StringEncoding];
    a[(__bridge id)kSecAttrAccessible] = (__bridge id)kSecAttrAccessibleAfterFirstUnlock;
    SecItemAdd((__bridge CFDictionaryRef)a, NULL);
}

- (UITextField *)fieldWithPlaceholder:(NSString *)ph y:(CGFloat)y secure:(BOOL)secure width:(CGFloat)w {
    CGRect b = self.window.rootViewController.view.bounds;
    UITextField *f = [[UITextField alloc] initWithFrame:CGRectMake((b.size.width - w) / 2, y, w, 44)];
    f.backgroundColor = [UIColor colorWithWhite:1 alpha:0.92];
    f.layer.cornerRadius = 14;
    f.layer.borderWidth = 3;
    f.layer.borderColor = [UIColor colorWithRed:0.12 green:0.30 blue:0.65 alpha:1].CGColor;
    f.font = [UIFont fontWithName:@"MarkerFelt-Wide" size:24] ?: [UIFont boldSystemFontOfSize:22];
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
    CGFloat w = MIN(b.size.width * 0.5, 380);
    CGFloat y0 = b.size.height * (self.logoView ? 0.47 : 0.36);
    self.loginView = [[UIView alloc] initWithFrame:b];
    self.loginView.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    self.userField = [self fieldWithPlaceholder:@"Toon name" y:y0 secure:NO width:w];
    self.passField = [self fieldWithPlaceholder:@"Password" y:y0 + 52 secure:YES width:w];
    self.userField.text = [[NSUserDefaults standardUserDefaults] stringForKey:@"ttr_user"];
    self.passField.text = [self keychainPassword];
    self.playButton = [UIButton buttonWithType:UIButtonTypeCustom];
    self.playButton.frame = CGRectMake((b.size.width - 220) / 2, y0 + 106, 220, 48);
    self.playButton.backgroundColor = [UIColor colorWithRed:1.0 green:0.85 blue:0.15 alpha:1];
    self.playButton.layer.cornerRadius = 18;
    self.playButton.layer.borderWidth = 4;
    self.playButton.layer.borderColor = [UIColor colorWithRed:0.55 green:0.32 blue:0.05 alpha:1].CGColor;
    [self.playButton setTitle:@"PLAY!" forState:UIControlStateNormal];
    [self.playButton setTitleColor:[UIColor colorWithRed:0.45 green:0.22 blue:0.02 alpha:1] forState:UIControlStateNormal];
    self.playButton.titleLabel.font = [UIFont fontWithName:@"MarkerFelt-Wide" size:30] ?: [UIFont boldSystemFontOfSize:28];
    [self.playButton addTarget:self action:@selector(signIn) forControlEvents:UIControlEventTouchUpInside];
    self.loginError = [[UILabel alloc] initWithFrame:CGRectMake(40, y0 + 160, b.size.width - 80, 26)];
    self.loginError.textAlignment = NSTextAlignmentCenter;
    self.loginError.font = [UIFont fontWithName:@"MarkerFelt-Wide" size:17] ?: [UIFont boldSystemFontOfSize:16];
    self.loginError.textColor = [UIColor colorWithRed:0.1 green:0.25 blue:0.55 alpha:1];
    self.loginError.text = @"New here? Pick a name and password and tap PLAY!";
    self.loginView.userInteractionEnabled = YES;
    self.userField.userInteractionEnabled = YES;
    self.passField.userInteractionEnabled = YES;
    for (UIView *x in @[self.userField, self.passField, self.playButton, self.loginError]) [self.loginView addSubview:x];
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
        NSString *code = [NSString stringWithFormat:@"import ios_game\n_r = ios_game.check_login('%@', '%@')\n", RESOURCE_SERVER, cookie];
        NSString *r = pyString(code.UTF8String, "_r");
        dispatch_async(dispatch_get_main_queue(), ^{
            if ([r isEqualToString:@"ok"]) {
                [[NSUserDefaults standardUserDefaults] setObject:user forKey:@"ttr_user"];
                [self saveKeychainPassword:pw];
                [self.loginView removeFromSuperview];
                self.loginWindow.hidden = YES;
                self.loginWindow = nil;
                [[NSNotificationCenter defaultCenter] removeObserver:self];
                self.statusLabel.hidden = NO;
                self.statusLabel.text = @"Starting Toontown...";
                [self.spinner startAnimating];
                dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.3 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
                    [self launchGameWithCookie:cookie];
                });
            } else {
                self.playButton.enabled = YES;
                [self loginMessage:(r ?: @"Sign-in failed.") bad:YES];
            }
        });
    });
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
        [self docsPath], [self fwPath], GAME_SERVER, cookie, [[self resPath] stringByAppendingPathComponent:@"."]];
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
        self.window.hidden = YES;   // the game has its own window underneath: do not cover it
        [self showControls];
    } else {
        [self showError:g];
    }
}

- (void)tick:(CADisplayLink *)link {
    static int n = 0;
    n++;
    if (n <= 3 || n % 300 == 0) fprintf(stderr, "TICK %d\n", n);
    pyRun("import ios_game\nios_game.step()\n");
    if (n <= 3) fprintf(stderr, "TICK %d done\n", n);
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

    CGFloat js = 150;
    JoystickView *joy = [[JoystickView alloc] initWithFrame:CGRectMake(MAX(safe.left, 24) + 20, b.size.height - js - MAX(safe.bottom, 16) - 24, js, js)];
    [vc.view addSubview:joy];
    CGFloat jb = 92;
    JumpButton *jump = [[JumpButton alloc] initWithFrame:CGRectMake(b.size.width - jb - MAX(safe.right, 24) - 30, b.size.height - jb - MAX(safe.bottom, 16) - 130, jb, jb)];
    [vc.view addSubview:jump];

    UIView *hot = [[UIView alloc] initWithFrame:CGRectMake(b.size.width / 2 - 50, 0, 100, 40)];   // top centre: nothing in the game lives here
    hot.backgroundColor = [UIColor clearColor];
    UITapGestureRecognizer *five = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(toggleLog)];
    five.numberOfTapsRequired = 5;
    [hot addGestureRecognizer:five];
    [vc.view addSubview:hot];
    self.controls.hidden = NO;
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
        NSString *code = [NSString stringWithFormat:
            @"import ios_game\nios_game.start_download('%@', '%@')\n", [self docsPath], RESOURCE_SERVER];
        pyRun(code.UTF8String);
        self.poll = [NSTimer scheduledTimerWithTimeInterval:0.25 target:self selector:@selector(pollDownload:) userInfo:nil repeats:YES];
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
