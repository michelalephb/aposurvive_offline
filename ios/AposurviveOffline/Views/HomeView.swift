import SwiftUI

/// Screen 1: triage home.
struct HomeView: View {
    @EnvironmentObject private var app: AppModel
    @EnvironmentObject private var model: ModelService
    @EnvironmentObject private var device: DeviceGuard
    @State private var draft = ""
    @State private var route: ChatRoute?

    private let columns = [GridItem(.flexible(), spacing: 8), GridItem(.flexible(), spacing: 8)]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            statusRow
            if !app.readiness.offlineOK { setupBanner }
            Text("What is happening?").font(.title3.weight(.semibold))
            LazyVGrid(columns: columns, spacing: 8) {
                ForEach(app.categories) { cat in
                    Button { route = ChatRoute(category: cat.id, question: nil) } label: { tile(cat) }
                        .buttonStyle(.plain)
                }
            }
            if let err = app.libraryError {
                Text(err).font(.footnote).foregroundStyle(.red)
            }
            Spacer()
            askField
        }
        .padding()
        .navigationTitle("Aposurvive")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                NavigationLink { FieldCardsView() } label: { Image(systemName: "rectangle.stack") }
                    .accessibilityLabel("Field cards")
            }
        }
        .navigationDestination(item: $route) { r in ChatView(categoryId: r.category, initialQuestion: r.question) }
        .onAppear { device.refresh(); app.refreshReadiness() }
    }

    private var statusRow: some View {
        HStack(spacing: 6) {
            if app.readiness.offlineOK {
                StatusPill(text: "Offline OK", symbol: "wifi.slash", tint: .green)
            } else {
                StatusPill(text: "Not ready", symbol: "exclamationmark.triangle", tint: .orange)
            }
            StatusPill(text: modelText)
            if let reason = device.pauseReason { StatusPill(text: reason, symbol: "bolt.slash", tint: .orange) }
            Spacer()
            Text(device.batteryText).font(.caption).foregroundStyle(.secondary)
        }
    }

    private var modelText: String {
        switch model.state {
        case .ready: return "Model ready"
        case .notLoaded: return "Model on device"
        case .loading: return "Loading model"
        case .downloading(let p): return "Downloading \(Int(p * 100))%"
        case .notDownloaded: return "No model"
        case .failed: return "Model error"
        }
    }

    private var setupBanner: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Finish setup while you still have internet").font(.subheadline.weight(.semibold))
            Text("Library: \(app.readiness.libraryDetail)").font(.caption)
            Text("Model: \(app.readiness.modelDetail)").font(.caption)
            if case .failed(let msg) = model.state { Text(msg).font(.caption).foregroundStyle(.red) }
            if !app.readiness.modelOK {
                Button("Download model (about 2.3 GB, use wifi)") { Task { await app.downloadModel() } }
                    .font(.caption.weight(.semibold))
                    .disabled({ if case .downloading = model.state { return true } else { return false } }())
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 10))
    }

    private func tile(_ cat: SurvivalCategory) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Image(systemName: cat.symbol).font(.title3)
            Text(cat.label).font(.subheadline)
        }
        .frame(maxWidth: .infinity, minHeight: 64, alignment: .leading)
        .padding(10)
        .background(cat.isUrgent ? Color.red.opacity(0.16) : Color.secondary.opacity(0.08),
                    in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10)
            .stroke(cat.isUrgent ? Color.red.opacity(0.6) : Color.secondary.opacity(0.25), lineWidth: 0.5))
        .foregroundStyle(cat.isUrgent ? .red : .primary)
    }

    private var askField: some View {
        HStack {
            TextField("Describe your situation", text: $draft, axis: .vertical)
                .lineLimit(1...3)
                .submitLabel(.send)
                .onSubmit(send)
            Button(action: send) { Image(systemName: "arrow.up.circle.fill").font(.title2) }
                .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .padding(10)
        .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.secondary.opacity(0.4), lineWidth: 0.5))
    }

    private func send() {
        let q = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !q.isEmpty else { return }
        route = ChatRoute(category: nil, question: q)
        draft = ""
    }
}

struct ChatRoute: Hashable, Identifiable {
    let id = UUID()
    let category: String?
    let question: String?
}
