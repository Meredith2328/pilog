package io.github.meredith2328.pilogwrite;

import android.os.Bundle;
import android.os.SystemClock;

import androidx.core.splashscreen.SplashScreen;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    /** Keep the splash up until the write UI has painted, but never longer than this. */
    private static final long SPLASH_MAX_MS = 2500;

    static volatile boolean webReady = false;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        SplashScreen splash = SplashScreen.installSplashScreen(this);
        long start = SystemClock.uptimeMillis();
        webReady = false;
        splash.setKeepOnScreenCondition(() -> !webReady && SystemClock.uptimeMillis() - start < SPLASH_MAX_MS);
        registerPlugin(PilogSecurePlugin.class);
        super.onCreate(savedInstanceState);
        PilogSecurePlugin.applySavedTheme(this, getBridge().getWebView());
    }
}
