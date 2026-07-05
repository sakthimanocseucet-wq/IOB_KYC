package com.iob.kyc.model;

import jakarta.persistence.*;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

@Data
@NoArgsConstructor
@AllArgsConstructor
@Builder
@Entity
@Table(name = "sessions")
public class Session {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private Long userId;

    @Column(nullable = false, unique = true)
    private String sessionToken;

    private Long deviceFingerprintId;

    private String ipAddress;

    private boolean active;

    private LocalDateTime startedAt;

    private LocalDateTime lastActivity;

    private LocalDateTime expiresAt;
}
