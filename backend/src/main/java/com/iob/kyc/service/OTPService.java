package com.iob.kyc.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.lang.Nullable;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

@Service
public class OTPService {

    private static final Logger log = LoggerFactory.getLogger(OTPService.class);

    private final HttpClient httpClient = HttpClient.newHttpClient();
    private final JavaMailSender mailSender;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Value("${resend.api-key:}")
    private String resendApiKey;

    @Value("${resend.from-email:onboarding@resend.dev}")
    private String resendFromEmail;

    @Value("${spring.mail.username:}")
    private String gmailFromEmail;

    public OTPService(@Nullable JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    @Async
    public void sendOtpEmail(String to, String otp) {
        String subject = "Your IOB KYC Verification Code";
        String htmlContent = buildOtpEmailHtml(otp);
        String plainText = "Your IOB KYC verification OTP is: " + otp + "\n\nThis code expires in 5 minutes. Do not share it with anyone.";
        sendEmail(to, subject, htmlContent, plainText);
    }

    @Async
    public void sendKycApprovedEmail(String to, String name, String applicationRef) {
        String subject = "KYC Verification Approved - IOB";
        String htmlContent = buildKycApprovedHtml(name, applicationRef);
        String plainText = "Dear " + name + ", Your KYC has been APPROVED. Ref: " + applicationRef;
        sendEmail(to, subject, htmlContent, plainText);
    }

    @Async
    public void sendKycRejectedEmail(String to, String name, String applicationRef, String reason) {
        String subject = "KYC Verification Requires Attention - IOB";
        String htmlContent = buildKycRejectedHtml(name, applicationRef, reason);
        String plainText = "Dear " + name + ", KYC needs review. Ref: " + applicationRef + " Reason: " + reason;
        sendEmail(to, subject, htmlContent, plainText);
    }

    private void sendEmail(String to, String subject, String htmlContent, String plainText) {
        boolean sent = false;

        if (resendApiKey != null && !resendApiKey.isEmpty()) {
            sent = sendViaResend(to, subject, htmlContent, plainText);
        }

        if (!sent && gmailFromEmail != null && !gmailFromEmail.isEmpty()) {
            sendViaGmail(to, subject, htmlContent, plainText);
        }
    }

    private boolean sendViaResend(String to, String subject, String htmlContent, String plainText) {
        try {
            ObjectNode json = objectMapper.createObjectNode();
            json.put("from", resendFromEmail);
            ArrayNode toArray = objectMapper.createArrayNode();
            toArray.add(to);
            json.set("to", toArray);
            json.put("subject", subject);
            json.put("text", plainText);
            json.put("html", htmlContent);
            json.put("reply_to", gmailFromEmail);

            String jsonString = objectMapper.writeValueAsString(json);

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create("https://api.resend.com/emails"))
                    .header("Authorization", "Bearer " + resendApiKey)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(jsonString))
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200) {
                log.info("Email sent to {} via Resend", to);
                return true;
            } else {
                log.warn("Resend failed ({}): {}, falling back to Gmail", response.statusCode(), response.body());
                return false;
            }
        } catch (Exception e) {
            log.warn("Resend error: {}, falling back to Gmail", e.getMessage());
            return false;
        }
    }

    private void sendViaGmail(String to, String subject, String htmlContent, String plainText) {
        if (mailSender == null) {
            log.warn("Gmail SMTP not configured — skipping email to {}", to);
            return;
        }
        try {
            MimeMessage message = mailSender.createMimeMessage();
            MimeMessageHelper helper = new MimeMessageHelper(message, true, "UTF-8");
            helper.setFrom("IOB KYC System <" + gmailFromEmail + ">");
            helper.setReplyTo(gmailFromEmail);
            helper.setTo(to);
            helper.setSubject(subject);
            helper.setText(plainText, htmlContent);
            mailSender.send(message);
            log.info("Email sent to {} via Gmail SMTP", to);
        } catch (MessagingException e) {
            log.error("Gmail SMTP failed for {}: {}", to, e.getMessage());
        }
    }

    private String buildOtpEmailHtml(String otp) {
        StringBuilder sb = new StringBuilder();
        sb.append("<!DOCTYPE html><html><head><meta charset=\"UTF-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\"></head>");
        sb.append("<body style=\"margin:0;padding:0;background:#f4f6f8;font-family:'Segoe UI',Arial,sans-serif\">");
        sb.append("<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#f4f6f8;padding:40px 0\">");
        sb.append("<tr><td align=\"center\">");
        sb.append("<table width=\"520\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.08)\">");
        sb.append("<tr><td style=\"background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:36px 32px;text-align:center\">");
        sb.append("<h1 style=\"color:#ffffff;margin:0;font-size:26px;font-weight:700\">IOB KYC System</h1>");
        sb.append("<p style=\"color:rgba(255,255,255,0.9);margin:8px 0 0;font-size:14px\">Identity Verification Service</p>");
        sb.append("</td></tr>");
        sb.append("<tr><td style=\"padding:44px 40px;text-align:center\">");
        sb.append("<h2 style=\"color:#1e293b;margin:0 0 12px;font-size:22px\">Email Verification</h2>");
        sb.append("<p style=\"color:#64748b;margin:0 0 28px;font-size:15px;line-height:1.5\">Please use the following One-Time Password to verify your identity:</p>");
        sb.append("<table cellpadding=\"0\" cellspacing=\"0\" style=\"margin:0 auto 28px\">");
        sb.append("<tr><td style=\"background:#f1f5f9;border-radius:10px;padding:20px 48px;border:2px dashed #94a3b8;text-align:center\">");
        sb.append("<span style=\"font-size:40px;font-weight:800;letter-spacing:10px;color:#1e3a5f;font-family:'Courier New',monospace\">").append(otp).append("</span>");
        sb.append("</td></tr></table>");
        sb.append("<table cellpadding=\"0\" cellspacing=\"0\" style=\"margin:0 auto 0;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden\">");
        sb.append("<tr><td style=\"padding:10px 20px;text-align:center\">");
        sb.append("<span style=\"color:#dc2626;font-weight:700;font-size:13px\">EXPIRES IN 5 MINUTES</span>");
        sb.append("</td></tr></table>");
        sb.append("<p style=\"color:#94a3b8;margin:28px 0 0;font-size:13px;line-height:1.5\">If you did not request this verification, please ignore this email. Do not share this code with anyone.</p>");
        sb.append("</td></tr>");
        sb.append("<tr><td style=\"background:#f8fafc;padding:20px 40px;text-align:center;border-top:1px solid #e2e8f0\">");
        sb.append("<p style=\"color:#94a3b8;margin:0;font-size:12px\">This is an automated message from IOB Digital KYC System. Please do not reply.</p>");
        sb.append("</td></tr></table></td></tr></table></body></html>");
        return sb.toString();
    }

    private String buildKycApprovedHtml(String name, String applicationRef) {
        StringBuilder sb = new StringBuilder();
        sb.append("<!DOCTYPE html><html><head><meta charset=\"UTF-8\"></head>");
        sb.append("<body style=\"margin:0;padding:0;background:#f4f6f8;font-family:'Segoe UI',Arial,sans-serif\">");
        sb.append("<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#f4f6f8;padding:40px 0\">");
        sb.append("<tr><td align=\"center\">");
        sb.append("<table width=\"520\" style=\"background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.08)\">");
        sb.append("<tr><td style=\"background:linear-gradient(135deg,#16a34a,#22c55e);padding:36px;text-align:center\">");
        sb.append("<h1 style=\"color:#fff;margin:0;font-size:24px\">KYC Approved</h1></td></tr>");
        sb.append("<tr><td style=\"padding:40px;text-align:center\">");
        sb.append("<h2 style=\"color:#16a34a;margin:0 0 16px\">Verification Complete!</h2>");
        sb.append("<p style=\"color:#475569\">Dear <strong>").append(escapeHtml(name)).append("</strong>,</p>");
        sb.append("<p style=\"color:#475569\">Your KYC has been <strong style=\"color:#16a34a\">approved</strong>.</p>");
        sb.append("<p style=\"color:#64748b\">Reference: <strong>").append(escapeHtml(applicationRef)).append("</strong></p></td></tr></table></td></tr></table>");
        sb.append("</body></html>");
        return sb.toString();
    }

    private String buildKycRejectedHtml(String name, String applicationRef, String reason) {
        StringBuilder sb = new StringBuilder();
        sb.append("<!DOCTYPE html><html><head><meta charset=\"UTF-8\"></head>");
        sb.append("<body style=\"margin:0;padding:0;background:#f4f6f8;font-family:'Segoe UI',Arial,sans-serif\">");
        sb.append("<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#f4f6f8;padding:40px 0\">");
        sb.append("<tr><td align=\"center\">");
        sb.append("<table width=\"520\" style=\"background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 12px rgba(0,0,0,0.08)\">");
        sb.append("<tr><td style=\"background:linear-gradient(135deg,#dc2626,#ef4444);padding:36px;text-align:center\">");
        sb.append("<h1 style=\"color:#fff;margin:0;font-size:24px\">KYC Requires Attention</h1></td></tr>");
        sb.append("<tr><td style=\"padding:40px;text-align:center\">");
        sb.append("<h2 style=\"color:#dc2626;margin:0 0 16px\">Verification Not Approved</h2>");
        sb.append("<p style=\"color:#475569\">Dear <strong>").append(escapeHtml(name)).append("</strong>,</p>");
        sb.append("<p style=\"color:#475569\">Your KYC needs additional review.</p>");
        sb.append("<p style=\"color:#64748b\">Reference: <strong>").append(escapeHtml(applicationRef)).append("</strong></p>");
        sb.append("<p style=\"color:#64748b\">Reason: ").append(escapeHtml(reason)).append("</p></td></tr></table></td></tr></table>");
        sb.append("</body></html>");
        return sb.toString();
    }

    private String escapeHtml(String input) {
        if (input == null) return "";
        return input.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    .replace("\"", "&quot;").replace("'", "&#x27;");
    }
}
