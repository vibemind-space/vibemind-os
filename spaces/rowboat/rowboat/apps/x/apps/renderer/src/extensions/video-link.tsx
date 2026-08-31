/**
 * Video Link Extension for TipTap
 *
 * Detects markdown links pointing to .mp4/.webm/.mov files and renders
 * them as inline <video> players instead of clickable text links.
 *
 * Works with the VibeMind media server (localhost:8977) and any other
 * video URL.
 */

import { Node, mergeAttributes } from '@tiptap/react'
import { ReactNodeViewRenderer, NodeViewWrapper } from '@tiptap/react'
import { Plugin, PluginKey } from '@tiptap/pm/state'
import { useState, useRef } from 'react'
import { Play, Pause, Maximize2, Volume2, VolumeX } from 'lucide-react'

const VIDEO_EXTENSIONS = /\.(mp4|webm|mov|avi)(\?.*)?$/i

function VideoPlayerView({ node }: { node: { attrs: { src: string; title: string } } }) {
  const { src, title } = node.attrs
  const videoRef = useRef<HTMLVideoElement>(null)
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState(false)

  const togglePlay = () => {
    if (!videoRef.current) return
    if (playing) {
      videoRef.current.pause()
    } else {
      videoRef.current.play()
    }
    setPlaying(!playing)
  }

  return (
    <NodeViewWrapper className="video-link-wrapper" data-type="video-link" contentEditable={false}>
      <div style={{
        borderRadius: '8px',
        overflow: 'hidden',
        background: '#111',
        margin: '8px 0',
        maxWidth: '100%',
      }}>
        <video
          ref={videoRef}
          src={src}
          style={{ width: '100%', display: 'block', maxHeight: '400px' }}
          controls
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
        />
        {title && (
          <div style={{
            padding: '6px 10px',
            fontSize: '12px',
            color: '#999',
            background: '#1a1a1a',
          }}>
            {title}
          </div>
        )}
      </div>
    </NodeViewWrapper>
  )
}

export const VideoLinkExtension = Node.create({
  name: 'videoLink',
  group: 'block',
  atom: true,
  selectable: true,
  draggable: false,

  addAttributes() {
    return {
      src: { default: '' },
      title: { default: '' },
    }
  },

  parseHTML() {
    return [
      {
        tag: 'div[data-type="video-link"]',
        getAttrs(element) {
          const video = element.querySelector('video')
          return {
            src: video?.getAttribute('src') || '',
            title: element.getAttribute('data-title') || '',
          }
        },
      },
    ]
  },

  renderHTML({ HTMLAttributes }: { HTMLAttributes: Record<string, unknown> }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-type': 'video-link' })]
  },

  addNodeView() {
    return ReactNodeViewRenderer(VideoPlayerView)
  },

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: new PluginKey('videoLinkTransform'),
        appendTransaction: (_transactions, _oldState, newState) => {
          let tr = newState.tr
          let modified = false

          newState.doc.descendants((node, pos) => {
            // Find paragraph nodes that contain a single link to a video file
            if (node.type.name !== 'paragraph') return
            if (node.childCount !== 1) return

            const child = node.firstChild
            if (!child || !child.isText) return

            const linkMark = child.marks.find(m => m.type.name === 'link')
            if (!linkMark) return

            const href = linkMark.attrs.href as string
            if (!VIDEO_EXTENSIONS.test(href)) return

            // Replace the paragraph+link with a videoLink node
            const videoNode = newState.schema.nodes.videoLink?.create({
              src: href,
              title: child.text || '',
            })
            if (videoNode) {
              tr = tr.replaceWith(pos, pos + node.nodeSize, videoNode)
              modified = true
            }
          })

          return modified ? tr : null
        },
      }),
    ]
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: { write: (text: string) => void; closeBlock: (node: unknown) => void }, node: { attrs: { src: string; title: string } }) {
          const title = node.attrs.title || '▶ Video abspielen'
          state.write(`[${title}](${node.attrs.src})`)
          state.closeBlock(node)
        },
      },
    }
  },
})
