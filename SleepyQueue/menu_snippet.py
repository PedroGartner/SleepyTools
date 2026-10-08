# Sleepy Queue integration
try:
    import sleepy_queue_nuke_integration as _bg

    _bg.install_menu()
except Exception as _bg_error:
    print("Sleepy Queue integration:", _bg_error)
