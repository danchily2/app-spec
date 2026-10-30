struct PayslipItem {
    let period: String
    let netPay: String
}

struct PayslipDocument {
    let url: String
}

enum PayslipStrings {
    static let latest = "payslip.latest"
    static let listTitle = "payslip.list.title"
    static let pdf = "payslip.pdf"
}
