import SwiftUI

struct PayslipListView: View {
    let items: [String]

    var body: some View {
        NavigationStack {
            List(items, id: \.self) { item in
                Text(item)
            }
            .navigationTitle("Payslips")
            Text("Your payslips")
                .accessibilityIdentifier("pay.list.title")
            Button("Refresh") {}
        }
    }
}
