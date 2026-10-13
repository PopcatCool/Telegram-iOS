// MARK: Burmaldagram
import SGSimpleSettings
import SGItemListUI
import Foundation
import UIKit
import Display
import SwiftSignalKit
import TelegramPresentationData
import ItemListUI
import AccountContext

private enum BurmaldaSection: Int32, SGItemListSection {
    case ghost
    case messages
}

private enum BurmaldaBoolSetting: String {
    case ghostDontRead
    case ghostDontSendOnline
    case ghostDontSendTyping
    case ghostDontSendPlayed
    case keepDeletedMessages
}

private typealias BurmaldaEntry = SGItemListUIEntry<BurmaldaSection, BurmaldaBoolSetting, AnyHashable, AnyHashable, AnyHashable, AnyHashable>

private func burmaldaEntries(presentationData: PresentationData) -> [BurmaldaEntry] {
    let isRussian = presentationData.strings.baseLanguageCode == "ru"
    let t: (String, String) -> String = { ru, en in
        return isRussian ? ru : en
    }

    var entries: [BurmaldaEntry] = []
    let id = SGItemListCounter()

    entries.append(.header(id: id.count, section: .ghost, text: t("РЕЖИМ ПРИЗРАКА", "GHOST MODE"), badge: nil))
    entries.append(.toggle(id: id.count, section: .ghost, settingName: .ghostDontRead, value: SGSimpleSettings.shared.ghostDontRead, text: t("Не читать сообщения", "Don't read messages"), enabled: true))
    entries.append(.notice(id: id.count, section: .ghost, text: t("Открытый чат остаётся непрочитанным. Прочитать можно через «Пометить как прочитанное» в списке чатов или отправив сообщение.", "An opened chat stays unread. Use \"Mark as Read\" in the chat list or send a message to read it.")))
    entries.append(.toggle(id: id.count, section: .ghost, settingName: .ghostDontSendOnline, value: SGSimpleSettings.shared.ghostDontSendOnline, text: t("Не показывать «в сети»", "Don't send online status"), enabled: true))
    entries.append(.notice(id: id.count, section: .ghost, text: t("После отправки сообщения статус «в сети» может появиться на срок до 30 секунд.", "After sending a message the online status may appear for up to 30 seconds.")))
    entries.append(.toggle(id: id.count, section: .ghost, settingName: .ghostDontSendTyping, value: SGSimpleSettings.shared.ghostDontSendTyping, text: t("Не показывать «печатает»", "Don't send typing status"), enabled: true))
    entries.append(.toggle(id: id.count, section: .ghost, settingName: .ghostDontSendPlayed, value: SGSimpleSettings.shared.ghostDontSendPlayed, text: t("Не отмечать прослушанное", "Don't send played status"), enabled: true))
    entries.append(.notice(id: id.count, section: .ghost, text: t("Голосовые, кружки и одноразовые медиа не помечаются у отправителя как открытые.", "Voice messages, video messages and view-once media are not marked as opened for the sender.")))

    entries.append(.header(id: id.count, section: .messages, text: t("СООБЩЕНИЯ", "MESSAGES"), badge: nil))
    entries.append(.toggle(id: id.count, section: .messages, settingName: .keepDeletedMessages, value: SGSimpleSettings.shared.keepDeletedMessages, text: t("Сохранять удалённые сообщения", "Keep deleted messages"), enabled: true))
    entries.append(.notice(id: id.count, section: .messages, text: t("Сообщения, удалённые собеседником, остаются в чате на этом устройстве.", "Messages deleted by the other side stay in the chat on this device.")))

    return entries
}

public func burmaldaSettingsController(context: AccountContext) -> ViewController {
    let simplePromise = ValuePromise(true, ignoreRepeated: false)

    let arguments = SGItemListArguments<BurmaldaBoolSetting, AnyHashable, AnyHashable, AnyHashable, AnyHashable>(
        context: context,
        setBoolValue: { setting, value in
            switch setting {
            case .ghostDontRead:
                SGSimpleSettings.shared.ghostDontRead = value
            case .ghostDontSendOnline:
                SGSimpleSettings.shared.ghostDontSendOnline = value
            case .ghostDontSendTyping:
                SGSimpleSettings.shared.ghostDontSendTyping = value
            case .ghostDontSendPlayed:
                SGSimpleSettings.shared.ghostDontSendPlayed = value
            case .keepDeletedMessages:
                SGSimpleSettings.shared.keepDeletedMessages = value
            }
            simplePromise.set(true)
        }
    )

    let signal = combineLatest(simplePromise.get(), context.sharedContext.presentationData)
    |> map { _, presentationData -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let entries = burmaldaEntries(presentationData: presentationData)

        let controllerState = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text("Burmaldagram"), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))

        let listState = ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: entries, style: .blocks, ensureVisibleItemTag: nil, initialScrollToItem: nil)

        return (controllerState, (listState, arguments))
    }

    return ItemListController(context: context, state: signal)
}
