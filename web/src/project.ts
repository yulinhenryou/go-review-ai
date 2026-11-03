// The product name is provisional; config/project.json is its only source.
import project from '../../config/project.json'

export interface ProjectInfo {
  name: string
  slug: string
  provisional: boolean
  tagline: string
}

export const projectInfo: ProjectInfo = project
