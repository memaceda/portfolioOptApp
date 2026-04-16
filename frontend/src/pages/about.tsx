import DownloadCard from '../components/DownloadCard';

import about from '../static/about';

const Download = () => {
    return (
        <div>
            <div className="flex flex-wrap gap-8">
                {about.map(elem => {
                    return <DownloadCard title={elem.title} img_path={elem.img_path} info={elem.info} redirect={elem.redirect} key={elem.id} />
                })}
            </div>

        </div>
    );
};

export default Download;