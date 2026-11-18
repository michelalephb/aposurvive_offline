import Foundation

/// Top level state shared by all screens.
@MainActor
final class AppModel: ObservableObject {
    let library: LibraryStore?
    let libraryError: String?
    let model: ModelService
    let device: DeviceGuard
    let torch: SOSTorch
    let systemPrompt: String

    @Published private(set) var readiness = Readiness()

    init() {
        model = ModelService()
        device = DeviceGuard()
        torch = SOSTorch()
        systemPrompt = PromptBuilder.systemPrompt
        do {
            guard let url = Bundle.main.url(forResource: "library", withExtension: "sqlite") else {
                throw LibraryError.missing("library.sqlite")
            }
            library = try LibraryStore(url: url)
            libraryError = nil
        } catch {
            library = nil
            libraryError = error.localizedDescription
        }
    }

    var categories: [SurvivalCategory] { library?.categories ?? [] }

    func category(_ id: String?) -> SurvivalCategory? {
        guard let id else { return nil }
        return categories.first { $0.id == id }
    }

    func refreshReadiness() {
        readiness = Readiness.check(library: library)
    }

    /// Loads the model if it is on disk. Never starts a download on its own.
    func warmUpIfPossible() async {
        refreshReadiness()
        if ModelService.isDownloaded && device.aiAllowed { await model.load() }
    }

    func downloadModel() async {
        await model.load()
        refreshReadiness()
    }
}
