import base64
import functools
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.write_live'


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def current_path(page):
    return page.evaluate('window.__pilogWrite.pathOf(window.__pilogWrite.current())')


def export_note(page, expected_name, text):
    page.locator('[data-open="export"]').click()
    with page.expect_download() as event:
        page.locator('#btn-download').click()
    download = event.value
    assert download.suggested_filename == expected_name, download.suggested_filename
    destination = OUT / 'downloads' / expected_name
    download.save_as(destination)
    assert text in destination.read_text(encoding='utf-8')
    page.locator('#sheet-export [data-close]').click()


def main():
    OUT.mkdir(exist_ok=True)
    handler = functools.partial(Handler, directory=str(ROOT / 'mobile' / 'www'))
    with ThreadingHTTPServer(('127.0.0.1', 0), handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(downloads_path=str(OUT / 'downloads'))
                context = browser.new_context(viewport={'width': 390, 'height': 844}, accept_downloads=True)
                page = context.new_page()
                page.goto(f'http://127.0.0.1:{server.server_port}/index.html')
                page.wait_for_function('() => window.__pilogWrite && window.__pilogWrite.current()')

                page.locator('#f-title').fill('同日中文稿件')
                page.locator('#f-body').fill('第一篇独立内容')
                expect(page.locator('#save-t')).to_have_text('已保存')
                first_path = current_path(page)
                first_name = Path(first_path).name
                assert re.fullmatch(r'post-\d{8}-\d{6}\.md', first_name), first_name
                assert first_name.startswith('post-' + page.locator('#f-date').input_value().replace('-', '') + '-')
                export_note(page, first_name, '第一篇独立内容')
                page.reload()
                page.wait_for_function('() => window.__pilogWrite && window.__pilogWrite.current()')
                assert current_path(page) == first_path

                page.locator('#btn-drafts').click()
                page.locator('#btn-new').click()
                page.locator('#f-title').fill('同日中文稿件')
                page.locator('#f-body').fill('第二篇独立内容')
                expect(page.locator('#save-t')).to_have_text('已保存')
                second_path = current_path(page)
                second_name = Path(second_path).name
                assert re.fullmatch(r'post-\d{8}-\d{6}\.md', second_name), second_name
                assert first_path != second_path
                export_note(page, second_name, '第二篇独立内容')
                expect(page.locator('#doc-path')).to_contain_text(second_name)
                page.wait_for_function('() => getComputedStyle(document.querySelector("#scrim")).opacity === "0"')
                page.wait_for_function('() => !document.querySelector("#toast").classList.contains("is-on")')
                page.screenshot(path=str(OUT / 'filenames.png'), full_page=True)
                print('通过：同日同标题稿件的实际导出文件不同，文件名包含六位数字并在刷新后保持稳定。')

                page.locator('#f-title').fill('Same title')
                expect(page.locator('#save-t')).to_have_text('已保存')
                assert current_path(page) == second_path
                page.locator('#btn-drafts').click()
                page.locator('#btn-new').click()
                page.locator('#f-title').fill('Same title')
                page.locator('#f-body').fill('第三篇独立内容')
                expect(page.locator('#save-t')).to_have_text('已保存')
                third_path = current_path(page)
                third_name = Path(third_path).name
                assert re.fullmatch(r'post-\d{8}-\d{6}\.md', third_name), third_name
                assert third_path != second_path
                export_note(page, third_name, '第三篇独立内容')
                print('通过：同日同名英文标题也使用不同的默认文件名。')

                page.locator('[data-view="meta"]').click()
                page.locator('#f-slug').fill('custom-file')
                page.locator('#f-slug').press('Tab')
                assert current_path(page).endswith('/custom-file.md')
                page.locator('#f-slug').fill('')
                page.locator('#f-slug').press('Tab')
                assert current_path(page) == third_path
                assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
                print('通过：自定义文件名有效，清空后恢复该稿件原来的默认文件名。')

                day = page.locator('#f-date').input_value()
                imported_name = 'post-' + day.replace('-', '') + '-000000.md'
                imported_file = OUT / imported_name
                imported_file.write_text(f'---\ntitle: 导入稿件\ndate: {day}\n---\n\n导入内容\n', encoding='utf-8')
                page.locator('#file-in').set_input_files(imported_file)
                expect(page.locator('#f-body')).to_have_value('导入内容\n')
                assert Path(current_path(page)).name == imported_name
                page.locator('#btn-drafts').click()
                page.locator('#btn-new').click()
                page.locator('#f-body').fill('导入后的新稿件')
                expect(page.locator('#save-t')).to_have_text('已保存')
                assert Path(current_path(page)).name != imported_name
                print('通过：导入稿件保留文件名，新稿件使用独立编号。')

                page.locator('#btn-drafts').click()
                page.locator('#sheet-drafts [data-open="remote"]').click()
                expect(page.locator('#pk select').first).to_be_enabled(timeout=60000)
                page.locator('#pk select').nth(0).select_option('d:toy')
                page.screenshot(path=str(OUT / 'picker.png'), full_page=True)
                assert not page.locator('#rm-adv').evaluate('el => el.open')
                with page.expect_response(
                    lambda response: '/contents/blogs/posts/toy/10pi.md' in response.url,
                    timeout=60000,
                ) as response_event:
                    page.locator('#pk select').nth(1).select_option('f:10pi.md')
                response = response_event.value
                assert response.ok, response.status
                remote = response.json()
                page.wait_for_function(
                    '() => window.__pilogWrite.current().src && window.__pilogWrite.current().src.path === "blogs/posts/toy/10pi.md"',
                    timeout=60000,
                )
                draft = page.evaluate('window.__pilogWrite.current()')
                assert draft['src']['sha'] == remote['sha']
                assert len(draft['body'].strip()) > 100
                assert draft['body'].strip() in base64.b64decode(remote['content']).decode('utf-8')
                assert current_path(page) == 'blogs/posts/toy/10pi.md'
                page.screenshot(path=str(OUT / 'online-post.png'), full_page=True)
                print('通过：从真实线上目录逐级选择文章并载入 GitHub 原文，无需输入链接。')
                browser.close()
        finally:
            server.shutdown()
            thread.join()


if __name__ == '__main__':
    main()
