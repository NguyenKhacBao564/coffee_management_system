// Keychain helper. Secret stdout is only consumed by the worker's private pipe.
import Foundation
import Security
let args = CommandLine.arguments
func query(_ service: String) -> [String: Any] {
    return [kSecClass as String: kSecClassGenericPassword, kSecAttrAccount as String: "pilot", kSecAttrService as String: service]
}
if args.count == 3 && args[1] == "import-file" {
    let data = try Data(contentsOf: URL(fileURLWithPath: args[2]))
    let credentials = try JSONSerialization.jsonObject(with: data) as! [String:Any]
    for field in ["username", "password"] {
        let q = query("nhu-tung-camera-185-runtime-" + field)
        let value = (credentials[field] as! String).data(using: .utf8)!
        var attributes = q; attributes[kSecValueData as String] = value
        let status = SecItemAdd(attributes as CFDictionary, nil)
        if status != errSecSuccess && status != errSecDuplicateItem { print("KEYCHAIN_IMPORT_FAILED"); exit(1) }
    }
    print("KEYCHAIN_IMPORT_OK")
} else if args.count == 3 && args[1] == "read" {
    var q = query(args[2]); q[kSecReturnData as String] = true; q[kSecMatchLimit as String] = kSecMatchLimitOne
    var result: CFTypeRef?
    let status = SecItemCopyMatching(q as CFDictionary, &result)
    guard status == errSecSuccess, let data = result as? Data else { exit(2) }
    FileHandle.standardOutput.write(data)
} else { exit(2) }
