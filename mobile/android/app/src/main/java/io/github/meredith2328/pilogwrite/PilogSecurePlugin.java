package io.github.meredith2328.pilogwrite;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyPermanentlyInvalidatedException;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import android.view.WindowManager;

import androidx.annotation.NonNull;
import androidx.biometric.BiometricManager;
import androidx.biometric.BiometricPrompt;
import androidx.core.content.ContextCompat;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Small secrets bridge for the write UI:
 * - get/set/remove: values encrypted with a non-exportable AES-GCM Android Keystore key
 *   (used for the GitHub token), ciphertext kept in private SharedPreferences;
 * - bio*: the vault data key wrapped by a second Keystore key that only works after a
 *   BIOMETRIC_STRONG prompt and is invalidated when biometrics change;
 * - setSecure: FLAG_SECURE while the vault is open (no screenshots / recents preview).
 */
@CapacitorPlugin(name = "PilogSecure")
public class PilogSecurePlugin extends Plugin {

    private static final String STORE = "AndroidKeyStore";
    private static final String PREFS = "pilog.secure";
    private static final String KEY_PREFS = "pilog.secure.v1";
    private static final String KEY_BIO = "pilog.vault.bio.v1";
    private static final String BIO_BLOB = "__vault_bio";

    private SharedPreferences prefs() {
        return getContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private SecretKey key(String alias, boolean bio) throws Exception {
        KeyStore ks = KeyStore.getInstance(STORE);
        ks.load(null);
        if (ks.containsAlias(alias)) return (SecretKey) ks.getKey(alias, null);
        KeyGenerator gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, STORE);
        KeyGenParameterSpec.Builder spec = new KeyGenParameterSpec.Builder(alias,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256);
        if (bio) {
            spec.setUserAuthenticationRequired(true).setInvalidatedByBiometricEnrollment(true);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                spec.setUserAuthenticationParameters(0, KeyProperties.AUTH_BIOMETRIC_STRONG);
            }
        }
        gen.init(spec.build());
        return gen.generateKey();
    }

    private static void deleteKey(String alias) {
        try {
            KeyStore ks = KeyStore.getInstance(STORE);
            ks.load(null);
            ks.deleteEntry(alias);
        } catch (Exception ignored) {
        }
    }

    private static String pack(byte[] iv, byte[] ct) {
        return Base64.encodeToString(iv, Base64.NO_WRAP) + ":" + Base64.encodeToString(ct, Base64.NO_WRAP);
    }

    @PluginMethod
    public void get(PluginCall call) {
        String k = call.getString("key");
        String blob = k == null ? null : prefs().getString(k, null);
        JSObject ret = new JSObject();
        if (blob == null) {
            ret.put("value", "");
            call.resolve(ret);
            return;
        }
        try {
            String[] p = blob.split(":");
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.DECRYPT_MODE, key(KEY_PREFS, false), new GCMParameterSpec(128, Base64.decode(p[0], Base64.NO_WRAP)));
            ret.put("value", new String(c.doFinal(Base64.decode(p[1], Base64.NO_WRAP)), StandardCharsets.UTF_8));
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("secure read failed", e);
        }
    }

    @PluginMethod
    public void set(PluginCall call) {
        String k = call.getString("key"), v = call.getString("value", "");
        if (k == null || k.startsWith("__")) {
            call.reject("invalid key");
            return;
        }
        try {
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.ENCRYPT_MODE, key(KEY_PREFS, false));
            byte[] ct = c.doFinal(v.getBytes(StandardCharsets.UTF_8));
            prefs().edit().putString(k, pack(c.getIV(), ct)).apply();
            call.resolve();
        } catch (Exception e) {
            call.reject("secure write failed", e);
        }
    }

    @PluginMethod
    public void remove(PluginCall call) {
        String k = call.getString("key");
        if (k != null && !k.startsWith("__")) prefs().edit().remove(k).apply();
        call.resolve();
    }

    @PluginMethod
    public void bioStatus(PluginCall call) {
        int s = BiometricManager.from(getContext()).canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_STRONG);
        JSObject ret = new JSObject();
        ret.put("available", s == BiometricManager.BIOMETRIC_SUCCESS);
        ret.put("enrolled", prefs().contains(BIO_BLOB));
        call.resolve(ret);
    }

    @PluginMethod
    public void bioEnroll(PluginCall call) {
        String secret = call.getString("secret");
        if (secret == null || secret.isEmpty()) {
            call.reject("missing secret");
            return;
        }
        try {
            deleteKey(KEY_BIO);
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.ENCRYPT_MODE, key(KEY_BIO, true));
            prompt(call, c, "开启指纹解锁", (cipher) -> {
                byte[] ct = cipher.doFinal(secret.getBytes(StandardCharsets.UTF_8));
                prefs().edit().putString(BIO_BLOB, pack(cipher.getIV(), ct)).apply();
                call.resolve();
            });
        } catch (Exception e) {
            call.reject("biometric setup failed", e);
        }
    }

    @PluginMethod
    public void bioUnlock(PluginCall call) {
        String blob = prefs().getString(BIO_BLOB, null);
        if (blob == null) {
            call.reject("biometric unlock not set up");
            return;
        }
        try {
            String[] p = blob.split(":");
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.DECRYPT_MODE, key(KEY_BIO, true), new GCMParameterSpec(128, Base64.decode(p[0], Base64.NO_WRAP)));
            prompt(call, c, call.getString("title", "解锁私密库"), (cipher) -> {
                byte[] pt = cipher.doFinal(Base64.decode(p[1], Base64.NO_WRAP));
                JSObject ret = new JSObject();
                ret.put("secret", new String(pt, StandardCharsets.UTF_8));
                call.resolve(ret);
            });
        } catch (KeyPermanentlyInvalidatedException e) {
            clearBio();
            call.reject("生物识别信息已变更，请用密码解锁后重新开启指纹解锁。");
        } catch (Exception e) {
            call.reject("biometric unlock failed", e);
        }
    }

    @PluginMethod
    public void bioClear(PluginCall call) {
        clearBio();
        call.resolve();
    }

    private void clearBio() {
        prefs().edit().remove(BIO_BLOB).apply();
        deleteKey(KEY_BIO);
    }

    @PluginMethod
    public void setSecure(PluginCall call) {
        boolean on = Boolean.TRUE.equals(call.getBoolean("on", false));
        getActivity().runOnUiThread(() -> {
            if (on) getActivity().getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
            else getActivity().getWindow().clearFlags(WindowManager.LayoutParams.FLAG_SECURE);
            call.resolve();
        });
    }

    private interface CipherStep {
        void run(Cipher cipher) throws Exception;
    }

    private void prompt(PluginCall call, Cipher cipher, String title, CipherStep step) {
        getActivity().runOnUiThread(() -> {
            BiometricPrompt bp = new BiometricPrompt(getActivity(), ContextCompat.getMainExecutor(getContext()),
                    new BiometricPrompt.AuthenticationCallback() {
                        @Override
                        public void onAuthenticationSucceeded(@NonNull BiometricPrompt.AuthenticationResult result) {
                            try {
                                BiometricPrompt.CryptoObject co = result.getCryptoObject();
                                step.run(co != null && co.getCipher() != null ? co.getCipher() : cipher);
                            } catch (Exception e) {
                                call.reject("biometric crypto failed", e);
                            }
                        }

                        @Override
                        public void onAuthenticationError(int code, @NonNull CharSequence msg) {
                            call.reject(msg.toString());
                        }
                    });
            BiometricPrompt.PromptInfo info = new BiometricPrompt.PromptInfo.Builder()
                    .setTitle(title)
                    .setSubtitle("pilog 私密库")
                    .setNegativeButtonText("用密码")
                    .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
                    .build();
            bp.authenticate(info, new BiometricPrompt.CryptoObject(cipher));
        });
    }
}
