import SwiftUI

/// Screen 2: sourced answer. Retrieval always runs; the model runs only when allowed.
/// With no model (not downloaded, battery low, too hot) the user still gets the
/// matching manual passages verbatim.
struct ChatView: View {
    let categoryId: String?
    let initialQuestion: String?

    @EnvironmentObject private var app: AppModel
    @EnvironmentObject private var model: ModelService
    @EnvironmentObject private var device: DeviceGuard

    @State private var turns: [ChatTurn] = []
    @State private var draft = ""
    @State private var busy = false
    @State private var openSource: LibraryChunk?
    @State private var generation: Task<Void, Never>?
    @State private var lastQuestion: String?

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 14) {
                        ForEach(turns) { turn in
                            TurnView(turn: turn, onSource: { openSource = $0 }, onCheck: { draft = $0 + " " })
                                .id(turn.id)
                        }
                    }
                    .padding()
                }
                .onChange(of: turns.last?.text) { _, _ in
                    if let id = turns.last?.id { proxy.scrollTo(id, anchor: .bottom) }
                }
            }
            inputBar
        }
        .navigationTitle(app.category(categoryId)?.label ?? "Ask")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $openSource) { SourceSheet(chunk: $0) }
        .onAppear {
            if turns.isEmpty, let q = initialQuestion { ask(q) }
        }
        .onDisappear { generation?.cancel() }
    }

    private var inputBar: some View {
        HStack {
            TextField(app.category(categoryId).map { "\($0.label): what is going on?" } ?? "Describe your situation",
                      text: $draft, axis: .vertical)
                .lineLimit(1...4)
            if busy {
                Button { generation?.cancel() } label: { Image(systemName: "stop.circle.fill").font(.title2) }
                    .accessibilityLabel("Stop")
            } else {
                Button { ask(draft) } label: { Image(systemName: "arrow.up.circle.fill").font(.title2) }
                    .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
                    .accessibilityLabel("Send")
            }
        }
        .padding(10)
        .background(.bar)
    }

    @MainActor
    private func ask(_ raw: String) {
        let typed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !typed.isEmpty, !busy else { return }
        draft = ""
        // follow ups keep the previous question as context for retrieval and the model
        let question = lastQuestion.map { "\($0). \(typed)" } ?? typed
        lastQuestion = question
        turns.append(ChatTurn(role: .user, text: typed))

        guard let library = app.library else {
            turns.append(ChatTurn(role: .blocked, text: "Library missing. Reinstall the app.", finished: true))
            return
        }
        let sources = library.search(question, category: categoryId, k: 3)

        let modelReady: Bool = { if case .ready = model.state { return true } else { return false } }()
        if !device.aiAllowed || !modelReady {
            let why = device.pauseReason ?? "Model not loaded"
            turns.append(ChatTurn(role: .libraryOnly,
                                  text: sources.isEmpty ? "\(why). No matching passage. Open Field cards." : "\(why). Closest manual passages:",
                                  sources: sources, finished: true))
            return
        }

        let user = PromptBuilder.userMessage(question: question,
                                             categoryLabel: app.category(categoryId)?.label,
                                             sources: sources)
        guard let stream = model.stream(system: app.systemPrompt, user: user) else { return }
        turns.append(ChatTurn(role: .assistant, text: "", sources: sources))
        let index = turns.count - 1
        busy = true
        generation = Task { @MainActor in
            let start = Date()
            var pieces = 0
            do {
                for try await piece in stream {
                    if Task.isCancelled { break }
                    pieces += 1
                    turns[index].text += piece
                }
            } catch {
                turns[index].text += "\n[generation error: \(error.localizedDescription)]"
            }
            let secs = Date().timeIntervalSince(start)
            if secs > 0 { turns[index].tokensPerSecond = Double(pieces) / secs }
            turns[index].finished = true
            busy = false
        }
    }
}

private struct TurnView: View {
    let turn: ChatTurn
    let onSource: (LibraryChunk) -> Void
    let onCheck: (String) -> Void

    var body: some View {
        switch turn.role {
        case .user:
            HStack {
                Spacer(minLength: 40)
                Text(turn.text)
                    .padding(10)
                    .background(Color.secondary.opacity(0.15), in: RoundedRectangle(cornerRadius: 12))
            }
        case .assistant:
            AnswerView(turn: turn, onSource: onSource, onCheck: onCheck)
        case .libraryOnly:
            VStack(alignment: .leading, spacing: 8) {
                StatusPill(text: turn.text, symbol: "book.closed", tint: .orange)
                ForEach(turn.sources) { s in
                    Button { onSource(s) } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(s.label).font(.caption.weight(.semibold)).foregroundStyle(.blue)
                            Text(s.text).font(.footnote).lineLimit(6).foregroundStyle(.primary)
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.secondary.opacity(0.3), lineWidth: 0.5))
                    }
                    .buttonStyle(.plain)
                }
            }
        case .blocked:
            Text(turn.text).foregroundStyle(.red)
        }
    }
}

private struct AnswerView: View {
    let turn: ChatTurn
    let onSource: (LibraryChunk) -> Void
    let onCheck: (String) -> Void

    var body: some View {
        let p = turn.parsed
        VStack(alignment: .leading, spacing: 8) {
            switch p.kind {
            case .answer:
                VStack(alignment: .leading, spacing: 4) {
                    Text("Do now").font(.subheadline.weight(.semibold)).foregroundStyle(.red)
                    ForEach(Array(p.steps.enumerated()), id: \.offset) { i, step in
                        Text("\(i + 1). \(step)").font(.body)
                    }
                }
                .padding(.leading, 8)
                .overlay(alignment: .leading) { Rectangle().fill(Color.red).frame(width: 3) }
            case .refusal:
                VStack(alignment: .leading, spacing: 4) {
                    Text("Not in library").font(.subheadline.weight(.semibold)).foregroundStyle(.orange)
                    Text(p.refusalText)
                }
            case .unknown:
                Text(turn.text.isEmpty ? "Thinking locally…" : turn.text)
                    .foregroundStyle(turn.finished ? .primary : .secondary)
            }

            let used = p.sourceRefs.compactMap { i in turn.sources.indices.contains(i - 1) ? turn.sources[i - 1] : nil }
            if !used.isEmpty {
                FlowRow {
                    ForEach(used) { s in Button { onSource(s) } label: { SourceChip(label: s.shortLabel) }.buttonStyle(.plain) }
                }
                Text("Sourced. Tap a chip to read the original page.").font(.caption).foregroundStyle(.secondary)
            } else if turn.finished && p.kind == .answer {
                StatusPill(text: "No source cited: treat with caution", symbol: "exclamationmark.triangle", tint: .orange)
            }

            if !p.checks.isEmpty {
                Text("Quick checks").font(.caption.weight(.semibold))
                FlowRow {
                    ForEach(p.checks, id: \.self) { c in Button { onCheck(c) } label: { CheckChip(text: c) }.buttonStyle(.plain) }
                }
            }

            if let tps = turn.tokensPerSecond {
                Text("Local · \(Int(tps.rounded())) tok/s").font(.caption2).foregroundStyle(.secondary)
            }
        }
    }
}
