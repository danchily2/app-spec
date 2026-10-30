import SwiftUI

struct PayslipDetailView: View {
    let title: String

    var body: some View {
        VStack {
            Text(title)
            Text("Net pay")
            TextField("Search lines", text: .constant(""))
            Button(action: {}) {
                Image(systemName: "square.and.arrow.up")
            }
        }
    }
}
