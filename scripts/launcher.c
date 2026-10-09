#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <wchar.h>
#include <stdlib.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR args, int show) {
    (void)instance; (void)previous; (void)show;
    WCHAR root[32768], python[32768], command[32768];
    DWORD size = GetModuleFileNameW(NULL, root, 32768);
    if (!size || size >= 32768) return 1;
    WCHAR *slash = wcsrchr(root, L'\\');
    if (!slash) return 1;
    *slash = L'\0';
    if (_snwprintf(python, 32768, L"%ls\\runtime\\pythonw.exe", root) < 0 ||
        _snwprintf(command, 32768, L"\"%ls\" -B \"%ls\\run.py\" %ls", python, root, args) < 0) return 1;
    STARTUPINFOW startup = {0}; startup.cb = sizeof(startup);
    PROCESS_INFORMATION process = {0};
    if (!CreateProcessW(python, command, NULL, NULL, FALSE, CREATE_UNICODE_ENVIRONMENT,
                        NULL, root, &startup, &process)) {
        MessageBoxW(NULL, L"Could not start the bundled runtime. Extract the entire archive before opening mgebot duel.",
                    L"mgebot duel", MB_OK | MB_ICONERROR);
        return 1;
    }
    CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(process.hProcess, &code);
    CloseHandle(process.hProcess);
    if (code != 0) {
        MessageBoxW(NULL, L"The application closed with an error. See application.log in %LOCALAPPDATA%\\mgebot-duel.",
                    L"mgebot duel", MB_OK | MB_ICONERROR);
    }
    return (int)code;
}
