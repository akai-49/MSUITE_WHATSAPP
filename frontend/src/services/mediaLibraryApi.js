/**
 * Media Library REST client.
 */
import { createApiClient } from './_factory'
import { RPC } from '@/shared/constants/api'

const call = createApiClient({ prefix: RPC.mediaLibrary, label: 'Media Library' })

export function checkExistingAsset(fileName, fileSize, contentHash = null) {
  return call('check_existing_asset', { file_name: fileName, file_size: fileSize, content_hash: contentHash })
}

export function listMedia(filters = {}) {
  return call('list_media', filters)
}

export function deleteMedia(fileNames, permanent = false) {
  return call('delete_media', { file_names: fileNames, permanent })
}

export function restoreMedia(fileNames) {
  return call('restore_media', { file_names: fileNames })
}

export function renameMedia(fileName, newName) {
  return call('rename_media', { file_name: fileName, new_name: newName })
}

export function duplicateMedia(fileName) {
  return call('duplicate_media', { file_name: fileName })
}

export function getLibraryStats(filters = {}) {
  return call('get_library_stats', filters)
}

export function createFolder(folderName, parentFolder = 'Home') {
  return call('create_folder', { folder_name: folderName, parent_folder: parentFolder })
}

export function moveMedia(fileNames, targetFolder) {
  return call('move_media', { file_names: fileNames, target_folder: targetFolder })
}

export function updateMediaMetadata(fileUrl, sourceModule = null, campaign = null, tags = null) {
  return call('update_media_metadata', { file_url: fileUrl, source_module: sourceModule, campaign, tags })
}
