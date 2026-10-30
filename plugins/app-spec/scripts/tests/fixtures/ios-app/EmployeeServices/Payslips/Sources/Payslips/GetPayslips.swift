struct GetPayslips: APIClientRequest {
    let id: String

    var method: HTTPMethod { .get }

    var path: String { "\(APIConstants.URL.v1)/employees/\(id)/payslips" }
}
