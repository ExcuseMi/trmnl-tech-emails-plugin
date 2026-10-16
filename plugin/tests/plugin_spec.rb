# frozen_string_literal: true

# Tech Emails, run with `trmnlp test` from plugin/. No network: the emails.json poll is mocked and the transform
# picks the one record. Four views, a short and a very long email, no recipients, a year-only date, no context,
# a chat of 2 and of 12 messages, a failed poll with and without a kept email, on an OG (1-bit) and an X (v2).
require 'json'

RSpec.describe 'Tech Emails' do
  let(:custom_fields) { { 'mode' => 'newest', 'show_context' => 'true', 'text_size' => 'normal' } }

  def email(**extra)
    { 'kind' => 'email', 'from' => 'Mark Zuckerberg', 'to' => ['David Ebersman'], 'cc' => [], 'date' => '2012-02-27',
      'subject' => 'Re: Instagram', 'excerpt' => 'One thing I am thinking about is whether we should buy them.',
      'context' => 'Zuckerberg was the chief executive of Facebook.',
      'source' => { 'title' => 'House Antitrust Subcommittee, 2020', 'url' => 'https://example.com', 'locator' => 'p. 3' } }.merge(extra)
  end

  def chat(count)
    names = ['Sam Altman', 'Mira Murati', 'Ilya Sutskever', 'Greg Brockman', 'Zed Quinn']
    { 'kind' => 'chat', 'date' => '2023-11-19', 'context' => 'A weekend of board turmoil.',
      'source' => { 'title' => 'Court exhibit', 'url' => 'https://example.com', 'locator' => 'p. 1' },
      'messages' => Array.new(count) { |i| { 'from' => names[i % 2], 'text' => "Message number #{i + 1} of the thread, said in one sentence." } } }
  end

  def mocks_for(*records) = { %r{emails\.json} => { json: records } }
  DEVICES = [{ device: 'og_png' }, { device: 'v2' }].freeze
  # colour screens: black, white, red and yellow (BWRY), and a 7-colour one; the cases that matter most for them
  COLOR_DEVICES = [{ device: 'og_bwry' }, { device: 'inky_impression_7_3', palette: 'color-7a' }].freeze
  COLOR_CASES = ['a short email', 'a very long email', 'a chat of 2', 'a chat of 12'].freeze
  VIEWS = %w[full half_horizontal half_vertical quadrant].freeze

  def screen(view, records, device: 'og_png', fields: {}, **opts)
    trmnl.render(view:, device:, mocks: mocks_for(*records), custom_fields: custom_fields.merge(fields), **opts)
  end

  it_behaves_like 'a publishable recipe' do
    let(:mocks) { mocks_for(email) }
  end

  CASES = {
    'a short email' => [-> { [email] }, /Re: Instagram/, /One thing I am thinking/],
    'a very long email' => [-> { [email('excerpt' => ('We should talk about the plan for the next quarter. ' * 14).strip)] }, /Re: Instagram/, /We should talk/],
    'no recipients' => [-> { [email('to' => [], 'cc' => [])] }, /Re: Instagram/, /One thing/],
    'a year-only date' => [-> { [email('date' => '2012')] }, /Re: Instagram/, /One thing/],
    'a missing context' => [-> { [email.reject { |k, _| k == 'context' }] }, /Re: Instagram/, /One thing/],
    'a chat of 2' => [-> { [chat(2)] }, /Sam Altman texts Mira Murati/, /Message number 1/],
    'a chat of 12' => [-> { [chat(12)] }, /Sam Altman texts Mira Murati/, /Message number 1\b/]
  }.freeze

  CASES.each do |name, (records, title, body)|
    VIEWS.each do |view|
      (DEVICES + (COLOR_CASES.include?(name) ? COLOR_DEVICES : [])).each do |dev|
        describe "#{name}, #{view} on #{dev[:device]} #{dev[:palette]}".strip do
          let(:page) { screen(view, instance_exec(&records), **dev) }

          it 'draws without overflow, errors or a leaked Liquid tag' do
            expect(page).to have_no_overflow
            expect(page).to have_no_problems
            expect(page).to have_no_leaked_text
          end

          it 'shows the title and the start of the text' do
            page.has_css?('.tp-body')
            expect(page).to have_text(title)
            expect(page).to have_text(body)
          end

          it 'cuts nothing in half: every visible message and line sits inside the body box' do
            page.has_css?('.tp-body')
            r = page.evaluate(<<~JS)
              (() => {
                const box = document.querySelector('.tp-body'), b = box.getBoundingClientRect();
                const vis = [...box.querySelectorAll('[data-msg],[data-more]')].filter((e) => e.style.display !== 'none');
                const last = vis[vis.length - 1].getBoundingClientRect();
                return { inside: last.bottom <= b.bottom + 1, clipped: box.scrollHeight - box.clientHeight };
              })()
            JS
            expect(r['inside']).to be(true)
            expect(r['clipped']).to be <= 1
          end
        end
      end
    end
  end

  it 'a chat of 12 on a small view keeps whole messages and ends with an ellipsis' do
    page = screen('half_horizontal', [chat(12)])
    page.has_css?('.tp-body')
    shown = page.evaluate("[...document.querySelectorAll('[data-msg]')].filter((e) => e.style.display !== 'none').length")
    expect(shown).to be_between(1, 11)
    expect(page.evaluate("document.querySelector('[data-more]').style.display")).to eq('')
  end

  it 'a chat of 2 shows every message and no ellipsis on the full view' do
    page = screen('full', [chat(2)], device: 'v2')
    page.has_css?('.tp-body')
    expect(page).to have_text('Message number 2')
    expect(page.evaluate("document.querySelector('[data-more]').style.display")).to eq('none')
  end

  it 'the full view has the header block, a rule, the context and the credit' do
    page = screen('full', [email('to' => %w[A B C D])])
    expect(page).to have_text('Re: Instagram')
    expect(page).to have_text('February 27, 2012')
    expect(page).to have_text('To: A, B +2')
    expect(page).to have_css('[data-rule]')
    expect(page).to have_text('Zuckerberg was the chief executive')
    expect(page).to have_text('Source: House Antitrust Subcommittee, 2020')
    expect(page).to have_css('.title_bar .instance', text: '2012')
  end

  it 'show_context off hides the background line; the half views never show it' do
    expect(screen('full', [email], fields: { 'show_context' => 'false' })).to have_no_text('Zuckerberg was the chief')
    expect(screen('half_horizontal', [email])).to have_no_text('Zuckerberg was the chief')
    expect(screen('half_horizontal', [email])).to have_no_text('Source:')
  end

  it 'an email without a subject gets a readable title, never "(no subject)"' do
    DEVICES.each do |dev|
      page = screen('full', [email('subject' => '(no subject)')], **dev)
      page.has_css?('.tp-t')
      expect(page.evaluate("document.querySelector('.tp-t').textContent")).to eq('Mark Zuckerberg emails David Ebersman')
      expect(page).to have_no_text('no subject')
    end
  end

  it 'a year-only date shows the year alone' do
    expect(screen('full', [email('date' => '2012')])).to have_css(".label", exact_text: "2012")
  end

  def font(page, sel = '.tp-text') = page.evaluate("parseFloat(getComputedStyle(document.querySelector('#{sel}')).fontSize)")

  # the size of the framework's own classes on this device, from a probe outside the body
  def native(page, cls)
    page.evaluate("(() => { const p = document.createElement('span'); p.className = '#{cls}'; document.querySelector('.view').appendChild(p); const f = parseFloat(getComputedStyle(p).fontSize); p.remove(); return f; })()")
  end

  it 'a short record is set big: larger than the base size, filling the box' do
    DEVICES.each do |dev|
      page = screen('full', [email], **dev)
      page.has_css?('.tp-body')
      expect(font(page)).to be > native(page, 'description')
      expect(font(page)).to be > native(page, 'description') * 1.4
    end
  end

  it 'a record too long for the box is set small, a short one big, and the title follows the size' do
    page = screen('full', [chat(12)])
    page.has_css?('.tp-body')
    short = screen('full', [email])
    expect(font(page)).to be < font(short)
    expect(font(short, '.tp-t')).to be > font(page, '.tp-t')
    expect(font(page)).to eq(native(page, 'description'))
  end

  it 'text_size large is a minimum: a long text never goes below the large size' do
    long = email('excerpt' => ('We should talk about the plan for the next quarter and what it means. ' * 14).strip)
    page = screen('full', [long], fields: { 'text_size' => 'large' })
    page.has_css?('.tp-body')
    expect(font(page)).to be >= native(page, 'description description--large') - 0.5
  end

  it 'a chat shows a name only when the sender changes' do
    msgs = [['Sundar', 'one'], ['Sundar', 'two'], ['Sergey', 'three'], ['Sundar', 'four']].map { |f, t| { 'from' => f, 'text' => t } }
    page = screen('full', [chat(1).merge('messages' => msgs)])
    page.has_css?('.tp-body')
    expect(page.evaluate("[...document.querySelectorAll('.tp-who')].map((e) => e.textContent)")).to eq(%w[Sundar Sergey Sundar])
    expect(page.evaluate("document.querySelectorAll('.tp-text').length")).to eq(4)
  end

  # a very long text is cut at a whole line: the clamp leaves no half line
  it 'a very long email ends on a whole line inside the box' do
    page = screen('full', [email('excerpt' => ('Long sentence to fill the line. ' * 80).strip)])
    page.has_css?('.tp-body')
    r = page.evaluate(<<~JS)
      (() => {
        const t = document.querySelector('.tp-text'), lh = parseFloat(getComputedStyle(t).lineHeight);
        return { h: t.offsetHeight, lh, box: document.querySelector('.tp-body').clientHeight };
      })()
    JS
    expect((r['h'] / r['lh']) % 1).to be_within(0.05).of(0).or be_within(0.05).of(1)
    expect(r['h']).to be <= r['box']
  end

  describe 'the poll fails' do
    let(:good) { email('subject' => 'Kept email', 'excerpt' => 'Kept body text.') }

    # what the transform stored after a good run
    let(:kept) { trmnl.transform(device: 'og_png', mocks: mocks_for(good), custom_fields:).state }

    [{ 'answers 500' => { status: 500, body: '' }, 'answers nothing' => { json: {} }, 'is not JSON' => { body: 'oops' },
       'is an empty list' => { json: [] }, 'cannot be reached' => { error: :reset } }].first.each do |name, answer|
      it "#{name}: the kept email is shown again" do
        page = trmnl.render(view: 'full', device: 'og_png', mocks: { '*' => answer }, custom_fields:, state: kept)
        expect(page).to have_text('Kept email')
        expect(page).to have_text('Kept body text.')
        expect(page).to have_no_text('No email')
        expect(page).to have_no_problems.and(have_no_leaked_text)
      end

      it "#{name}: a first-ever failure shows a clean No email state on every view" do
        VIEWS.each do |view|
          page = trmnl.render(view:, device: 'og_png', mocks: { '*' => answer }, custom_fields:)
          expect(page).to have_text('No email right now')
          expect(page).to have_no_problems.and(have_no_leaked_text).and(have_no_transform_error)
        end
      end
    end
  end

  describe 'colour' do
    let(:two) { [chat(5)] }

    def name_colors(page)
      page.has_css?('.tp-who')
      page.evaluate("[...document.querySelectorAll('.tp-who')].map((e) => getComputedStyle(e).color)")
    end

    it 'mono screens (1-bit, 4-grey X): names are black, the text is black, nothing grey' do
      [{ device: 'og_png' }, { device: 'v2' }].each do |dev|
        page = screen('full', two, **dev)
        expect(name_colors(page).uniq).to eq(['rgb(0, 0, 0)'])
        expect(page.evaluate("[...document.querySelectorAll('.tp-text')].map((e) => getComputedStyle(e).color).join()")).to match(/\A(rgb\(0, 0, 0\),?)+\z/)
      end
    end

    it 'a 7-colour screen: each person has a colour of their own, in order of first appearance, text stays black' do
      page = screen('full', two, device: 'inky_impression_7_3', palette: 'color-7a')
      colors = name_colors(page)
      expect(colors.uniq.size).to eq(2)
      expect(colors).not_to include('rgb(0, 0, 0)')
      expect(page.evaluate("getComputedStyle(document.querySelector('.tp-text')).color")).to eq('rgb(0, 0, 0)')
    end

    it 'BWRY and BWR screens: the first speaker red, the second black, text black' do
      %w[og_bwry waveshare_7_5_bwr].each do |dev|
        page = screen('full', two, device: dev)
        expect(name_colors(page).first(2)).to eq(['rgb(255, 0, 0)', 'rgb(0, 0, 0)'])
        expect(page.evaluate("getComputedStyle(document.querySelector('.tp-text')).color")).to eq('rgb(0, 0, 0)')
      end
    end
  end
end
