// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "SampleHR",
    platforms: [.iOS(.v16)],
    targets: [
        .target(name: "PayslipsFeature", path: "Modules/PayslipsFeature/Sources/PayslipsFeature"),
        .target(name: "Payslips", path: "EmployeeServices/Payslips/Sources/Payslips"),
    ]
)
