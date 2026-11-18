import Foundation
import MLXLLM
import MLXLMCommon

/// Loads and runs the on device model with MLX (mlx-swift-lm 2.30.x API).
/// First load needs internet once (downloads ~2.3 GB into Documents/huggingface).
/// After that the model is loaded from that local folder with no network calls.
@MainActor
final class ModelService: ObservableObject {
    enum State: Equatable {
        case notDownloaded
        case notLoaded          // on disk, not in memory
        case downloading(Double)
        case loading
        case ready
        case failed(String)
    }

    /// Swap for your fused fine tuned model repo once training is done.
    nonisolated static let modelID = "mlx-community/Qwen3-4B-Instruct-2507-4bit"

    @Published private(set) var state: State = .notDownloaded
    private var container: ModelContainer?

    init() {
        state = Self.isDownloaded ? .notLoaded : .notDownloaded
    }

    /// Default swift-transformers HubApi cache layout: Documents/huggingface/models/<repo id>.
    /// Verify on device the first time (the Readiness screen shows this path).
    nonisolated static var localDirectory: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("huggingface/models/\(modelID)", isDirectory: true)
    }

    nonisolated static var isDownloaded: Bool {
        let fm = FileManager.default
        let dir = localDirectory
        guard fm.fileExists(atPath: dir.appendingPathComponent("config.json").path),
              let files = try? fm.contentsOfDirectory(atPath: dir.path) else { return false }
        return files.contains { $0.hasSuffix(".safetensors") }
    }

    nonisolated static var downloadedBytes: Int64 {
        let fm = FileManager.default
        guard let files = try? fm.contentsOfDirectory(at: localDirectory, includingPropertiesForKeys: [.fileSizeKey]) else { return 0 }
        return files.reduce(0) { $0 + Int64((try? $1.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0) }
    }

    /// Loads from disk if present (offline), otherwise downloads (online only).
    func load() async {
        if case .ready = state { return }
        do {
            let configuration: ModelConfiguration
            if Self.isDownloaded {
                state = .loading
                configuration = ModelConfiguration(directory: Self.localDirectory)
            } else {
                state = .downloading(0)
                configuration = ModelConfiguration(id: Self.modelID)
            }
            let c = try await LLMModelFactory.shared.loadContainer(configuration: configuration) { progress in
                Task { @MainActor in
                    if case .downloading = self.state { self.state = .downloading(progress.fractionCompleted) }
                }
            }
            container = c
            state = .ready
        } catch {
            state = .failed(error.localizedDescription)
        }
    }

    func unload() {
        container = nil
        state = Self.isDownloaded ? .notLoaded : .notDownloaded
    }

    /// One shot generation: fresh session per question keeps memory and context small.
    func stream(system: String, user: String) -> AsyncThrowingStream<String, Error>? {
        guard let container else { return nil }
        let session = ChatSession(
            container,
            instructions: system,
            generateParameters: GenerateParameters(maxTokens: 400, temperature: 0.2)
        )
        return session.streamResponse(to: user)
    }
}
