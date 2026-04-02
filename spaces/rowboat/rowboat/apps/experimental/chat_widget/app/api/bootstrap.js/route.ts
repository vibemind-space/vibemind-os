export const dynamic = 'force-dynamic'

// Fetch template once when module loads
const templatePromise = fetch(process.env.CHAT_WIDGET_HOST + '/bootstrap.template.js')
  .then(res => res.text());

export async function GET() {
  try {
    // Reuse the cached content
    const template = await templatePromise;
    
    // Replace placeholder values with actual URLs
    const contents = template
      .replace('__CHAT_WIDGET_HOST__', process.env.CHAT_WIDGET_HOST || '')
      .replace('__ROWBOAT_HOST__', process.env.ROWBOAT_HOST || '');
    
    return new Response(contents, {
      headers: {
        'Content-Type': 'application/javascript',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
      },
    });
  } catch (error) {
    console.error('Error serving bootstrap.js:', error);
    return new Response('Error loading script', { status: 500 });
  }
}
