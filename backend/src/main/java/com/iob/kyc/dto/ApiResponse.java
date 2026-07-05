package com.iob.kyc.dto;

public class ApiResponse {

    private boolean success;
    private String message;
    private Object data;
    private int statusCode;

    public ApiResponse() {
    }

    public ApiResponse(boolean success, String message, Object data, int statusCode) {
        this.success = success;
        this.message = message;
        this.data = data;
        this.statusCode = statusCode;
    }

    public static ApiResponse success(String message, Object data) {
        return new ApiResponse(true, message, data, 200);
    }

    public static ApiResponse error(String message, int statusCode) {
        return new ApiResponse(false, message, null, statusCode);
    }

    public boolean isSuccess() {
        return success;
    }

    public void setSuccess(boolean success) {
        this.success = success;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }

    public Object getData() {
        return data;
    }

    public void setData(Object data) {
        this.data = data;
    }

    public int getStatusCode() {
        return statusCode;
    }

    public void setStatusCode(int statusCode) {
        this.statusCode = statusCode;
    }
}
