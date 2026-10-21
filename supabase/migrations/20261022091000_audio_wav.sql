-- 합성 음원은 대사 사이에 쉼을 넣어 WAV로 만들므로 audio 버킷에 WAV도 허용한다.
update storage.buckets
  set allowed_mime_types = array['audio/mpeg', 'audio/wav', 'audio/x-wav', 'audio/wave']
  where id = 'audio';
