struct GetPayslipPdf: APIClientRequest {
    let document: PayslipDocument

    var method: HTTPMethod { .get }

    var path: String { "\(APIConstants.URL.v1)/\(document.url)" }
}
