package io.github.meredith2328.pilogwrite;

import android.os.Bundle;
import android.os.SystemClock;
import android.widget.Toast;

import androidx.activity.OnBackPressedCallback;
import androidx.core.splashscreen.SplashScreen;

import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    /** Keep the splash up until the write UI has painted, but never longer than this. */
    private static final long SPLASH_MAX_MS = 2500;
    private static final long EXIT_CONFIRM_MS = 2000;

    private long lastBackPressedAt = 0;
    private Toast exitToast;

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
        exitToast = Toast.makeText(this, R.string.press_back_again_to_exit, Toast.LENGTH_SHORT);
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (getBridge().getWebView().canGoBack()) {
                    lastBackPressedAt = 0;
                    exitToast.cancel();
                    getBridge().getWebView().goBack();
                    return;
                }
                long now = SystemClock.elapsedRealtime();
                if (lastBackPressedAt != 0 && now - lastBackPressedAt < EXIT_CONFIRM_MS) {
                    exitToast.cancel();
                    finish();
                    return;
                }
                lastBackPressedAt = now;
                exitToast.show();
            }
        });
    }

    @Override
    public void onPause() {
        lastBackPressedAt = 0;
        if (exitToast != null) {
            exitToast.cancel();
        }
        super.onPause();
    }
}
