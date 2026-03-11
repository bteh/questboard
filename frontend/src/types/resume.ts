export interface ResumeStatus {
  profile: string;
  exists: boolean;
  filename: string;
  file_size: number;
  path: string;
}

export interface ResumeUploadResponse {
  profile: string;
  filename: string;
  message: string;
}
