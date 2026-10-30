import SwiftUI

struct PayslipCard: View {
    let item: PayslipItem

    var body: some View {
        VStack {
            Text("payslip.latest")
            Text(item.period)
        }
    }
}
