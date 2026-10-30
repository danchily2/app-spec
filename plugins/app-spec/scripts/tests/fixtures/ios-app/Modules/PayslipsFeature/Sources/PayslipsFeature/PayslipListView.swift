import SwiftUI

struct PayslipListView: View {
    let items: [String]

    var body: some View {
        NavigationStack {
            Text(String(localized: "payslip.list.title"))
                .accessibilityIdentifier("pay.list.title")
            List(items, id: \.self, rowContent: PayslipRow.init)
                .navigationTitle("Payslips")
            Button("Refresh") {}
        }
    }
}
