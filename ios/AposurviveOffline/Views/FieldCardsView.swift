import SwiftUI

/// Screen 3: no model fallback. Verbatim manual passages plus the SOS torch.
struct FieldCardsView: View {
    @EnvironmentObject private var app: AppModel
    @EnvironmentObject private var device: DeviceGuard
    @EnvironmentObject private var torch: SOSTorch

    var body: some View {
        List {
            if let reason = device.pauseReason {
                Section { StatusPill(text: reason, symbol: "bolt.slash", tint: .orange) }
            }
            Section("Static field cards") {
                ForEach(app.library?.fieldCards() ?? []) { card in
                    NavigationLink { FieldCardDetail(card: card) } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text(card.title).font(.subheadline.weight(.semibold))
                                if !card.reviewed { StatusPill(text: "Unreviewed", tint: .orange) }
                            }
                            Text(card.subtitle).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                }
            }
            Section {
                Button(action: torch.toggle) {
                    Label(torch.running ? "Stop SOS flashlight" : "SOS flashlight",
                          systemImage: torch.running ? "flashlight.on.fill" : "flashlight.off.fill")
                }
                .disabled(!torch.available)
            } footer: {
                Text("Same verified content as the AI uses, no model needed.")
            }
        }
        .navigationTitle("Field cards")
        .onDisappear { torch.stop() }
    }
}

private struct FieldCardDetail: View {
    let card: FieldCard
    @EnvironmentObject private var app: AppModel

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if !card.reviewed {
                    Text("Unreviewed: copied verbatim from the manual by search, not yet checked by a person.")
                        .font(.caption).foregroundStyle(.orange)
                }
                ForEach(app.library?.chunks(ids: card.chunkIds) ?? []) { chunk in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(chunk.label).font(.caption.weight(.semibold)).foregroundStyle(.blue)
                        Text(chunk.text).font(.body).textSelection(.enabled)
                    }
                }
            }
            .padding()
        }
        .navigationTitle(card.title)
        .navigationBarTitleDisplayMode(.inline)
    }
}
