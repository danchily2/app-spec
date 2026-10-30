package com.sample.hr.payslips

import retrofit2.http.GET
import retrofit2.http.Path

interface PayslipApi {
    @GET("employee/api/v1/employees/{id}/payslips")
    suspend fun payslips(@Path("id") id: String): List<String>
}
