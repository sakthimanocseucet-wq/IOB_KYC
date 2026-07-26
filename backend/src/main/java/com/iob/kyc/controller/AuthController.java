package com.iob.kyc.controller;

import com.iob.kyc.dto.ApiResponse;
import com.iob.kyc.dto.LoginRequest;
import com.iob.kyc.dto.RegisterRequest;
import com.iob.kyc.model.OtpCode;
import com.iob.kyc.service.AuthService;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseToken;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    // ====================== USER ENDPOINTS ======================

    @PostMapping("/register")
    public ResponseEntity<ApiResponse> register(@RequestBody RegisterRequest request) {
        ApiResponse response = authService.register(request);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    @PostMapping(value = "/login", consumes = "application/json")
    public ResponseEntity<ApiResponse> login(@RequestBody LoginRequest request) {
        ApiResponse response = authService.login(request);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    @PostMapping(value = "/login", consumes = "application/x-www-form-urlencoded")
    public ResponseEntity<ApiResponse> loginForm(@RequestParam String email, @RequestParam String password) {
        ApiResponse response = authService.login(new LoginRequest(email, password));
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    @PostMapping("/forgot-password/check")
    public ResponseEntity<ApiResponse> checkForgotPassword(@RequestBody Map<String, String> body) {
        String identifier = body.get("identifier");
        ApiResponse response = authService.checkForgotPassword(identifier);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    @PostMapping("/forgot-password/reset")
    public ResponseEntity<ApiResponse> resetPassword(@RequestBody Map<String, String> body) {
        String identifier = body.get("identifier");
        String newPassword = body.get("newPassword");
        ApiResponse response = authService.resetPassword(identifier, newPassword);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    // ====================== EMPLOYEE ENDPOINTS ======================

    @PostMapping("/admin/register")
    @org.springframework.security.access.prepost.PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<ApiResponse> registerEmployee(@RequestBody RegisterRequest request) {
        ApiResponse response = authService.registerEmployee(request);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    @PostMapping("/admin/login")
    public ResponseEntity<ApiResponse> adminLogin(@RequestBody Map<String, String> body) {
        String employeeId = body.get("employeeId");
        String password = body.get("password");
        ApiResponse response = authService.adminLogin(employeeId, password);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    @PostMapping("/admin/forgot-password/check")
    public ResponseEntity<ApiResponse> checkEmployeeForgotPassword(@RequestBody Map<String, String> body) {
        String identifier = body.get("identifier");
        ApiResponse response = authService.checkEmployeeForgotPassword(identifier);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    @PostMapping("/admin/forgot-password/reset")
    public ResponseEntity<ApiResponse> resetEmployeePassword(@RequestBody Map<String, String> body) {
        String identifier = body.get("identifier");
        String newPassword = body.get("newPassword");
        ApiResponse response = authService.resetEmployeePassword(identifier, newPassword);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    // ====================== OTP (shared) ======================

    @PostMapping("/otp/generate")
    public ResponseEntity<ApiResponse> generateOtp(
            @RequestParam String identifier,
            @RequestParam(defaultValue = "KYC") String purpose) {
        OtpCode.Purpose otpPurpose;
        try {
            otpPurpose = OtpCode.Purpose.valueOf(purpose.toUpperCase());
        } catch (Exception e) {
            otpPurpose = OtpCode.Purpose.KYC;
        }
        ApiResponse response = authService.generateOTP(identifier, otpPurpose);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    @PostMapping("/otp/verify")
    public ResponseEntity<ApiResponse> verifyOtp(
            @RequestParam String identifier,
            @RequestParam String otp,
            @RequestParam(defaultValue = "KYC") String purpose) {
        OtpCode.Purpose otpPurpose;
        try {
            otpPurpose = OtpCode.Purpose.valueOf(purpose.toUpperCase());
        } catch (Exception e) {
            otpPurpose = OtpCode.Purpose.KYC;
        }
        ApiResponse response = authService.verifyOTP(identifier, otp, otpPurpose);
        return ResponseEntity.status(response.getStatusCode()).body(response);
    }

    // ====================== EMAIL TEST ======================

    @PostMapping("/test-email")
    public ResponseEntity<java.util.Map<String, Object>> testEmail(@RequestBody Map<String, String> body) {
        String to = body.get("to");
        if (to == null || to.isEmpty()) {
            to = "test@example.com";
        }
        java.util.Map<String, Object> result = new java.util.HashMap<>();
        try {
            String apiKey = System.getenv("RESEND_API_KEY");
            String fromEmail = System.getenv("RESEND_FROM_EMAIL");
            result.put("apiKeySet", apiKey != null && !apiKey.isEmpty());
            result.put("apiKeyPrefix", apiKey != null && apiKey.length() > 4 ? apiKey.substring(0, 4) + "..." : "NOT SET");
            result.put("fromEmail", fromEmail != null ? fromEmail : "NOT SET (default: onboarding@resend.dev)");
            result.put("gmailUser", System.getenv("GMAIL_USERNAME") != null && !System.getenv("GMAIL_USERNAME").isEmpty());
            result.put("to", to);

            if (apiKey == null || apiKey.isEmpty()) {
                result.put("status", "BLOCKED");
                result.put("message", "RESEND_API_KEY env var is empty. Email cannot be sent.");
                return ResponseEntity.ok(result);
            }

            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            com.fasterxml.jackson.databind.node.ObjectNode json = mapper.createObjectNode();
            json.put("from", fromEmail != null && !fromEmail.isEmpty() ? fromEmail : "onboarding@resend.dev");
            com.fasterxml.jackson.databind.node.ArrayNode toArray = mapper.createArrayNode();
            toArray.add(to);
            json.set("to", toArray);
            json.put("subject", "IOB KYC - Test Email");
            json.put("text", "This is a test email from IOB KYC system. If you receive this, email OTP is working!");
            json.put("html", "<h2>IOB KYC Test Email</h2><p>Email OTP is working!</p><p>Your OTP will arrive at this address.</p>");

            java.net.http.HttpClient client = java.net.http.HttpClient.newHttpClient();
            java.net.http.HttpRequest request = java.net.http.HttpRequest.newBuilder()
                    .uri(java.net.URI.create("https://api.resend.com/emails"))
                    .header("Authorization", "Bearer " + apiKey)
                    .header("Content-Type", "application/json")
                    .POST(java.net.http.HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(json)))
                    .build();

            java.net.http.HttpResponse<String> response = client.send(request, java.net.http.HttpResponse.BodyHandlers.ofString());
            result.put("statusCode", response.statusCode());
            result.put("responseBody", response.body());

            if (response.statusCode() == 200) {
                result.put("status", "SUCCESS");
                result.put("message", "Test email sent successfully to " + to);
            } else {
                result.put("status", "FAILED");
                result.put("message", "Resend API returned error " + response.statusCode());
            }
        } catch (Exception e) {
            result.put("status", "ERROR");
            result.put("message", e.getMessage());
        }
        return ResponseEntity.ok(result);
    }

    // ====================== FIREBASE PHONE VERIFICATION ======================

    @PostMapping("/otp/verify-firebase")
    public ResponseEntity<ApiResponse> verifyFirebaseOtp(@RequestBody Map<String, String> body) {
        String idToken = body.get("idToken");
        String phone = body.get("phone");
        if (idToken == null || idToken.isEmpty()) {
            return ResponseEntity.badRequest().body(ApiResponse.error("Missing Firebase ID token", 400));
        }
        try {
            FirebaseToken token = FirebaseAuth.getInstance().verifyIdToken(idToken);
            Object phoneClaim = token.getClaims().get("phone_number");
            String firebasePhone = phoneClaim != null ? phoneClaim.toString() : null;
            if (firebasePhone == null) {
                return ResponseEntity.badRequest().body(ApiResponse.error("Token does not contain phone number", 400));
            }
            return ResponseEntity.ok(ApiResponse.success("Phone verified: " + firebasePhone, null));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(ApiResponse.error("Invalid Firebase token: " + e.getMessage(), 400));
        }
    }

}
