package com.iob.kyc.dto;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record KYCSubmitRequest(String docType, String ocrName, String ocrDob, String ocrIdNumber, String ocrPanNumber,
                                String ocrAddress, String mobile, String email, String accountType, String gender,
                                Integer riskScore, Double faceMatchPercent, Boolean livenessPassed,
                                String ipAddress,
                                String applicationType, Long existingAppId, String branch, String remarks) {
}

