import SwiftUI

@main
struct AposurviveApp: App {
    @StateObject private var app = AppModel()

    var body: some Scene {
        WindowGroup {
            NavigationStack {
                HomeView()
            }
            .environmentObject(app)
            .environmentObject(app.model)
            .environmentObject(app.device)
            .environmentObject(app.torch)
            .preferredColorScheme(.dark)
            .task { await app.warmUpIfPossible() }
        }
    }
}
