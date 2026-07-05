package com.iob.kyc.dto;

import jakarta.validation.constraints.*;

public record RegisterRequest(
    @NotBlank @Size(max = 50) String firstName,
    @NotBlank @Size(max = 50) String lastName,
    @NotBlank @Email @Size(max = 100) String email,
    @Pattern(regexp = "^\\+?[0-9]{10,15}$", message = "Invalid phone format") String phone,
    @NotBlank @Size(min = 8, max = 128) String password,
    String role,
    String employeeId
) {
}
